"""
downloaders/guobiao.py
国家标准下载器  openstd.samr.gov.cn/bzgk/gb/std_list

运行方式（由 process_manager 以子进程调用）：
  python -m downloaders.guobiao

环境变量（由 process_manager 注入）：
  DOWNLOADER_SOURCE_NAME     来源名称（必填）
  DOWNLOADER_SOURCE_URL      列表页 URL（必填）
  DOWNLOADER_DOWNLOAD_DIR    下载目录（默认 download/{name}）
  DOWNLOADER_SOURCE_ID       用于 should_stop() 的唯一 ID
"""

import os
import re
import sys
import time
import random

from playwright.sync_api import sync_playwright, Page, Download

from .common import (
    BaseDownloader, DownloadRecorder, create_browser_and_context,
    handle_download,
    should_stop, setup_stop_signal,
)


class GuobiaoDownloader(BaseDownloader):
    """
    国家标准  openstd.samr.gov.cn/bzgk/gb/std_list
    ─ 列表页用 URL 参数翻页（page=N）
    ─ 列表行：#, 标准号(a链接), 采标, 标准名称, ...
    ─ 详情页：button.xz_btn → 同页 .modal-dialog 验证码 → 下载
    ─ 国标列表含 p.p5=PUBLISHED，默认只含现行，无需再判断状态
    """

    def _list_page_tag(self):
        # std_list_ics 也包含 "std_list"，两种列表页均可匹配
        return "std_list"

    def _get_content_frame(self, page: Page):
        """
        std_list_ics 页面把表格和翻页控件放在 iframe 里。
        返回 iframe 的 Frame 对象；普通 std_list 页返回 page 本身。
        Frame 和 Page 接口相同，可直接用 query_selector_all 等方法。
        """
        if "std_list_ics" in page.url:
            frames = page.frames
            if len(frames) > 1:
                return frames[1]
        return page

    def _build_page_url(self, base_url: str, page_num: int) -> str:
        # std_list_ics 用 iframe 内点击翻页，不需要 URL 分页参数
        if "std_list_ics" in base_url or page_num <= 1:
            return base_url
        r = random.random()
        if "page=" in base_url:
            return re.sub(r"page=\d+", f"page={page_num}", base_url)
        sep = "&" if "?" in base_url else "?"
        return f"{base_url}{sep}r={r}&page={page_num}&pageSize=10"

    def _parse_rows(self, page: Page) -> list[dict]:
        frame = self._get_content_frame(page)
        is_ics = "std_list_ics" in page.url
        rows = []
        for tr in frame.query_selector_all("table tbody tr"):
            try:
                tds = tr.query_selector_all("td")
                if is_ics:
                    # ICS 列：标准号|是否采标|标准名称|标准分类|状态|发布日期|实施日期|操作
                    if len(tds) < 8:
                        continue
                    std_no   = tds[0].inner_text().strip()
                    std_name = tds[2].inner_text().strip()
                    is_adopted = bool(tds[1].inner_text().strip())
                    rows.append(dict(std_no=std_no, std_name=std_name,
                                     is_adopted=is_adopted,
                                     status=tds[4].inner_text().strip()))
                    continue
                else:
                    # 普通列：序号|标准号|采标(img)|标准名称|...
                    if len(tds) < 6:
                        continue
                    std_no   = tds[1].inner_text().strip()
                    std_name = tds[3].inner_text().strip()
                    is_adopted = False
                    try:
                        c = tds[2]
                        if c.query_selector("img") or c.inner_text().strip():
                            is_adopted = True
                    except Exception:
                        pass
                if not std_no or not std_name:
                    continue
                rows.append(dict(std_no=std_no, std_name=std_name, is_adopted=is_adopted))
            except Exception:
                continue
        return rows

    def _open_detail_page(self, list_page: Page, std_no: str) -> Page:
        """在列表页找到对应行的"查看详细"按钮，点击后等待新标签页打开。"""
        frame = self._get_content_frame(list_page)
        is_ics = "std_list_ics" in list_page.url
        # ICS: std_no 在 tds[0]；普通: std_no 在 tds[1]
        std_no_idx = 0 if is_ics else 1
        target_tr = None
        for tr in frame.query_selector_all("table tbody tr"):
            try:
                tds = tr.query_selector_all("td")
                if len(tds) > std_no_idx and tds[std_no_idx].inner_text().strip() == std_no:
                    target_tr = tr
                    break
            except Exception:
                continue

        if not target_tr:
            raise RuntimeError(f"列表页未找到 {std_no} 对应的行")

        btn = target_tr.query_selector("button")
        if not btn:
            raise RuntimeError(f"未找到 {std_no} 行的查看详细按钮")

        with self.context.expect_page(timeout=12000) as pg_info:
            btn.click()

        new_page = pg_info.value
        try:
            new_page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        time.sleep(2)
        return new_page

    def _download_one(self, row: dict, download_dir: str, source_name: str, list_page: Page = None) -> bool:
        std_no, std_name = row["std_no"], row["std_name"]

        # 废止标准 / 采标：不下载，只采集详情元数据后记录状态
        record_only_status = None
        if row.get("status") == "废止":
            record_only_status = "ABOLISHED"
        elif row.get("is_adopted"):
            record_only_status = "ADOPTED"

        if record_only_status:
            label = "废止标准" if record_only_status == "ABOLISHED" else "采标"
            print(f"   ○ {label}，只记录元数据", flush=True)
            detail_page = None
            try:
                detail_page = self._open_detail_page(list_page, std_no)
                self._parse_detail_meta(detail_page, source_name)
            except Exception as e:
                print(f"   ⚠ {label}详情获取失败：{e}", flush=True)
            finally:
                self._close_pages(detail_page)
            self.recorder.save(std_no, std_name, source_name, record_only_status)
            return False

        # 每次处理新标准前，关闭上次可能遗留的多余标签页（只保留 list_page）
        # 防止 c.gb688.cn 执行 window.opener.close() 等操作遗留的脏状态
        for _p in list(self.context.pages):
            if _p is not list_page:
                try:
                    _p.close()
                except Exception:
                    pass

        detail_page = None
        download_page = None
        try:
            detail_page = self._open_detail_page(list_page, std_no)
            self._parse_detail_meta(detail_page, source_name)

            dl_btn = self._find_download_btn(detail_page)
            if not dl_btn:
                body = detail_page.inner_text("body")
                if "暂无全文" in body or "等待更新" in body:
                    print(f"   ○ 暂无全文", flush=True)
                    self.recorder.save(std_no, std_name, source_name, "NO_FULL_TEXT")
                else:
                    print(f"   ⚠ 未找到下载按钮  URL={detail_page.url}", flush=True)
                return False

            # 外层重试：验证码页失效/所有内层重试耗尽时，重新打开验证码页（最多 5 次）
            for page_attempt in range(1, 6):
                download_page = None
                try:
                    dl_btn.evaluate("el => { el.classList.remove('app-hide'); el.scrollIntoView({block:'center'}); }")
                    time.sleep(0.5)

                    with self.context.expect_page(timeout=15000) as pg_info:
                        dl_btn.click()
                    download_page = pg_info.value
                    try:
                        download_page.wait_for_load_state("domcontentloaded", timeout=15000)
                    except Exception:
                        pass
                    time.sleep(1)

                    bucket: list[Download] = []
                    if self._solve_captcha(download_page, bucket):
                        dl = self._wait_download(bucket, timeout=5)
                        if not dl:
                            print(f"   ⚠ 等待下载超时", flush=True)
                            return False
                        result = handle_download(dl, download_dir, std_no, std_name, "guobiao")
                        self.recorder.save(std_no, std_name, source_name, "SUCCESS",
                                           oss_url=result.get("oss_url"),
                                           oss_path=result.get("oss_path"),
                                           local_path=result.get("local_path"))
                        return True

                except Exception as e:
                    print(f"   ⚠ 打开验证码页失败：{e}", flush=True)
                finally:
                    self._close_pages(download_page)

                if page_attempt < 5:
                    print(f"   ↺ 验证码失效，重新打开（{page_attempt}/5）...", flush=True)
                    try:
                        dl_btn = self._find_download_btn(detail_page)
                        if not dl_btn:
                            print(f"   ⚠ 详情页已失效，放弃", flush=True)
                            return False
                    except Exception:
                        print(f"   ⚠ 详情页已失效，放弃", flush=True)
                        return False
                    time.sleep(2)

            return False

        finally:
            self._close_pages(detail_page)

    def _parse_detail_meta(self, page: Page, source_name: str) -> None:
        """
        解析国标详情页元数据并写入 MySQL。
        异常时打印警告并静默跳过，不影响下载主流程。
        """
        try:
            from .db import upsert_guobiao_detail

            # ── 标准号（h1，去掉前缀"标准号："）────────────────────
            h1 = page.query_selector("h1")
            std_no = h1.inner_text().strip().replace("标准号：", "").strip() if h1 else ""
            if not std_no:
                return

            # ── 中文名称（第一个 b 标签）────────────────────────────
            b_el = page.query_selector("b")
            std_name_zh = b_el.inner_text().strip() if b_el else ""

            # ── 英文名称（td 文本含"英文标准名称："）────────────────
            std_name_en = ""
            for td in page.query_selector_all("td"):
                txt = td.inner_text().strip()
                if "英文标准名称：" in txt:
                    std_name_en = txt.replace("英文标准名称：", "").strip()
                    break

            # ── 标准状态（span 颜色区分）────────────────────────────
            # 采标页面：span.text-success 内为版权说明长文（>10字）→ 标记为"采标"（现行采标）
            # 废止/即将实施的采标：颜色 class 优先，仍存"废止"/"即将实施"
            status = ""
            for cls, val in (("span.text-success", "现行"),
                             ("span.text-danger",  "废止"),
                             ("span.text-warning", "即将实施")):
                el = page.query_selector(cls)
                if el:
                    text = el.inner_text().strip()
                    status = "采标" if (val == "现行" and len(text) > 10) else val
                    break

            # ── 强制/推荐性（从标准号推断）──────────────────────────
            if re.search(r"GB/Z", std_no, re.I):
                mandatory_type = "指导性"
            elif re.search(r"GB/T", std_no, re.I):
                mandatory_type = "推荐性"
            else:
                mandatory_type = "强制性"

            # ── .title + .content 键值对（JS 遍历相邻兄弟节点）─────
            fields: dict = page.evaluate("""() => {
                const f = {};
                document.querySelectorAll('.title').forEach(el => {
                    const key = el.innerText.trim();
                    if (!key) return;
                    const next = el.nextElementSibling;
                    if (next && next.classList.contains('content')) {
                        f[key] = next.innerText.trim();
                    }
                });
                return f;
            }""")

            # ── 备注（title div 父容器去掉 label 后的剩余文本）──────
            note = page.evaluate("""() => {
                const el = Array.from(document.querySelectorAll('.title'))
                    .find(e => e.innerText.trim() === '备注');
                if (!el) return '';
                const parent = el.parentElement;
                if (!parent) return '';
                const full = parent.innerText.trim();
                return full.replace(/^备注/, '').trim();
            }""") or None

            upsert_guobiao_detail({
                "std_no":         std_no,
                "std_name_zh":    std_name_zh or None,
                "std_name_en":    std_name_en or None,
                "mandatory_type": mandatory_type,
                "status":         status or None,
                "ccs":            fields.get("中国标准分类号（CCS）") or None,
                "ics":            fields.get("国际标准分类号（ICS）") or None,
                "publish_date":   fields.get("发布日期") or None,
                "implement_date": fields.get("实施日期") or None,
                "department":     fields.get("主管部门") or None,
                "org_department": fields.get("归口部门") or None,
                "publisher":      fields.get("发布单位") or None,
                "note":           note,
                "detail_url":     page.url,
                "source_name":    source_name,
            })

        except Exception as e:
            print(f"   ⚠ 国标元数据解析失败：{e}", flush=True)

    def _find_download_btn(self, page: Page):
        for sel in ("button.xz_btn", "button:has-text('下载标准')", "a:has-text('下载标准')"):
            try:
                page.wait_for_selector(sel, timeout=5000)
                btn = page.query_selector(sel)
                if btn:
                    return btn
            except Exception:
                pass
        return None

    def _solve_captcha(self, page: Page, bucket: list, max_retries: int = 5) -> bool:
        """
        国标验证码：c.gb688.cn 页面 .modal-dialog + #verifyCode

        通过 MCP 实测确认的完整 JS 流程（checkCode 函数）：
          1. window.open("url","_blank") → 立即打开新空白标签 winRef
          2. AJAX POST verifyCode 验证验证码
          3. 正确: winRef.location = "viewGb?hcno=..." → 下载在 winRef 触发
                   window.close() → 验证码页自身关闭
          4. 错误: winRef.close(); alert("验证码不正确..."); 刷新图片

        关键：下载发生在 winRef（新标签），不在验证码页本身。
        因此监听 context.expect_page 拿到 winRef，再在 winRef 上 expect_download。
        """
        try:
            page.wait_for_selector(".modal-dialog", timeout=10000)
            time.sleep(1)
        except Exception as e:
            print(f"   ⚠ 等待国标验证码界面超时：{e}", flush=True)
            return False

        for attempt in range(1, max_retries + 1):
            time.sleep(1)
            handle_dialog = None
            winref = None
            try:
                img_bytes = self._fetch_captcha_bytes(page)
                code = self._ocr(img_bytes)
                if len(code) != 4:
                    raise ValueError(f"识别结果长度不对：{code!r}")

                print(f"   [{attempt}/{max_retries}] 国标验证码：{code}", flush=True)

                inp = page.query_selector("#verifyCode")
                if not inp:
                    raise ValueError("未找到输入框 #verifyCode")
                inp.fill(code)

                btn = page.query_selector("button:has-text('验证')")
                if not btn:
                    raise ValueError("未找到验证按钮")

                # 监听 dialog：验证码错误时 alert("验证码不正确，请重新输入")
                error_msgs: list[str] = []
                def handle_dialog(dialog):
                    error_msgs.append(dialog.message)
                    dialog.accept()
                page.on("dialog", handle_dialog)

                # 点击验证按钮前先监听 context 级新页面（winRef = window.open(...)）
                # winRef 在 btn.click() 触发的 checkCode() 中同步创建，无需等很久
                download_triggered = False
                try:
                    with self.context.expect_page(timeout=8000) as winref_info:
                        btn.click()
                    winref = winref_info.value

                    # MCP 实测：Playwright 里 winRef.close()（来自网页 JS）不会真正关闭页面
                    # 因此不能靠 winref.is_closed() 判断验证码对错，也不能用阻塞式
                    # expect_download(timeout=15s) 等超时——错误路径会白等 15 秒。
                    #
                    # 正确做法：
                    #   - 在 winRef 上注册 download 监听器（非阻塞）
                    #   - 用 page.wait_for_timeout 轮询，同时处理两种信号：
                    #       * downloaded 有内容 → 验证码正确，下载已捕获
                    #       * error_msgs 有内容 → alert 触发 → 验证码错误，快速退出
                    #   - 4s 内未收到任何信号 → 用 expect_download 再等 12s（慢服务器兜底）
                    downloaded: list = []
                    def on_download(dl):
                        downloaded.append(dl)
                    winref.on("download", on_download)

                    # 轮询：最多 14 × 300ms ≈ 4.2s
                    for _ in range(14):
                        if error_msgs or downloaded:
                            break
                        try:
                            page.wait_for_timeout(300)
                        except Exception:
                            break  # 验证码页已被 window.close() 关闭

                    if downloaded:
                        bucket.append(downloaded[0])
                        download_triggered = True
                        print("   ✓ 国标验证码通过，下载已触发", flush=True)
                        return True
                    elif not error_msgs:
                        # 4s 内无 dialog 也无 download → 服务器较慢，继续等
                        try:
                            with winref.expect_download(timeout=12000) as dl_info:
                                pass
                            dl = dl_info.value
                            bucket.append(dl)
                            download_triggered = True
                            print("   ✓ 国标验证码通过，下载已触发", flush=True)
                            return True
                        except Exception:
                            pass

                    # 验证码错误（或超时）：Playwright 不关闭 winRef，需显式关闭
                    try:
                        winref.close()
                    except Exception:
                        pass
                    winref = None
                except Exception:
                    # window.open 未触发新页面（罕见），继续按验证码错误处理
                    pass

                try:
                    page.remove_listener("dialog", handle_dialog)
                    handle_dialog = None
                except Exception:
                    handle_dialog = None

                if not download_triggered:
                    # 验证码正确时网站会关闭验证码页（window.close()）
                    # 若已关闭说明下载已在 winRef 触发，但 expect_download 超时——放弃
                    if page.is_closed():
                        print("   ⚠ 验证码页被网站关闭，放弃重试", flush=True)
                        return False

                    # 清理遗留的 about:blank / "url" 空白页
                    for p in list(self.context.pages):
                        try:
                            if p.url in ("about:blank", "url", "") and p is not page:
                                p.close()
                        except Exception:
                            pass

                    if attempt < max_retries:
                        print("   ⚠ 验证码错误，刷新重试...", flush=True)
                        try:
                            self._refresh_captcha_img(page)
                            inp2 = page.query_selector("#verifyCode")
                            if inp2:
                                inp2.fill("")
                        except Exception:
                            print("   ⚠ 验证码页已失效，停止重试", flush=True)
                            return False
                        time.sleep(1)
                        continue
                    return False

            except Exception as e:
                if handle_dialog:
                    try:
                        page.remove_listener("dialog", handle_dialog)
                    except Exception:
                        pass
                if winref:
                    try:
                        winref.close()
                    except Exception:
                        pass
                if attempt < max_retries:
                    print(f"   ⚠ 识别出错({e})，刷新重试...", flush=True)
                    try:
                        self._refresh_captcha_img(page)
                    except Exception:
                        print("   ⚠ 验证码页已失效，停止重试", flush=True)
                        return False
                    time.sleep(1)
                else:
                    print(f"   ⚠ 国标验证码失败：{e}", flush=True)
                    return False
        return False

    def _fetch_captcha_bytes(self, page: Page) -> bytes:
        """截取验证码图片（screenshot 方式，避免 URL 请求 header 问题）。"""
        for sel in ("img.verifyCode", "img[class*='verify']", "img[title='']"):
            img_el = page.query_selector(sel)
            if img_el:
                return img_el.screenshot()
        # 兜底：找 src 含 gc? 或 verify 的图片
        for img in page.query_selector_all("img"):
            src = img.get_attribute("src") or ""
            if "gc?" in src or "verify" in src.lower():
                return img.screenshot()
        raise ValueError("未找到验证码图片")

    def _refresh_captcha_img(self, page: Page):
        refresh = (
            page.query_selector(".verifyCodeChange") or
            page.query_selector(".glyphicon-refresh")
        )
        if refresh:
            refresh.click()
            return
        try:
            page.evaluate("if(typeof refreshVerifyCode==='function') refreshVerifyCode()")
        except Exception:
            pass

    def _go_next_page(self, page: Page) -> bool:
        try:
            if page.is_closed():
                return False
        except Exception:
            return False

        # ── std_list_ics：iframe 内点击翻页按钮 ────────────────────────
        if "std_list_ics" in page.url:
            frame = self._get_content_frame(page)
            # 返回 [status, cur_page]：status=clicked 时 cur_page 为点击前页码
            result = frame.evaluate("""() => {
                const cells = Array.from(document.querySelectorAll('td, th'));
                for (const cell of cells) {
                    const m = cell.textContent.match(/(\\d+)\\s*\\/\\s*(\\d+)/);
                    if (!m) continue;
                    const cur = parseInt(m[1]), total = parseInt(m[2]);
                    if (cur >= total) return ['last', cur];
                    const row = cell.closest('tr');
                    if (!row) return ['no_row', cur];
                    const btns = Array.from(row.querySelectorAll('button'));
                    if (btns.length < 1) return ['no_btns', cur];
                    const nextBtn = btns[btns.length - 1];
                    if (nextBtn.disabled) return ['disabled', cur];
                    nextBtn.click();
                    return ['clicked', cur];
                }
                return ['not_found', 0];
            }""")
            status, cur_page = result[0], result[1]
            if status != "clicked":
                return False
            print("   → 翻页...", flush=True)
            # 等待分页数字变化（比 networkidle 更可靠，AJAX 数据加载完成标志）
            try:
                frame.wait_for_function(
                    f"() => {{ "
                    f"  var cells = Array.from(document.querySelectorAll('td,th'));"
                    f"  for (var i=0;i<cells.length;i++) {{"
                    f"    var m = cells[i].textContent.match(/(\\d+)\\s*\\/\\s*(\\d+)/);"
                    f"    if (m && parseInt(m[1]) > {cur_page}) return true;"
                    f"  }}"
                    f"  return false;"
                    f"}}",
                    timeout=15000,
                )
            except Exception:
                time.sleep(3)
            time.sleep(1)
            return True

        # ── std_list：URL 分页（原逻辑）────────────────────────────────
        next_btn = (
            page.query_selector("a.laypage_next") or
            page.query_selector("a:has-text('下一页')") or
            page.query_selector("a:has(span.glyphicon-menu-right)")
        )
        if not next_btn:
            return False
        cls = next_btn.get_attribute("class") or ""
        par = next_btn.evaluate("el => el.parentElement?.className || ''")
        if "disabled" in cls or "disabled" in par:
            return False
        next_btn.evaluate("el => el.scrollIntoView({behavior:'smooth',block:'center'})")
        next_btn.click()
        print("   → 翻页...", flush=True)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        time.sleep(2)
        return True


# ══════════════════════════════════════════════
#  子进程入口
# ══════════════════════════════════════════════

def main():
    source_name = os.environ.get("DOWNLOADER_SOURCE_NAME", "")
    source_url = os.environ.get("DOWNLOADER_SOURCE_URL", "")
    source_id = os.environ.get("DOWNLOADER_SOURCE_ID", source_name)
    download_dir = os.environ.get("DOWNLOADER_DOWNLOAD_DIR", os.path.join("download", source_name))

    if not source_name or not source_url:
        print("❌ 缺少环境变量 DOWNLOADER_SOURCE_NAME / DOWNLOADER_SOURCE_URL", flush=True)
        sys.exit(1)

    setup_stop_signal(source_id)   # 优雅退出：Ctrl+C / SIGTERM 等当前下载完再退出

    print(f"[国标] 来源：{source_name}", flush=True)
    print(f"[国标] URL：{source_url}", flush=True)
    print(f"[国标] 下载目录：{download_dir}", flush=True)

    source = {
        "name": source_name,
        "type": "guobiao",
        "url": source_url,
        "download_dir": download_dir,
    }
    recorder = DownloadRecorder(source_type="guobiao")
    recorder.load_from_db(source_name)

    with sync_playwright() as pw:
        browser, context = create_browser_and_context(pw)
        list_page = context.new_page()
        try:
            GuobiaoDownloader(context, recorder, source_id).download_source(source, list_page)
        finally:
            print("\n🎉 国标下载任务完成", flush=True)
            browser.close()


if __name__ == "__main__":
    main()
