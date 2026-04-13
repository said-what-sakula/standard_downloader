"""
downloaders/hangbiao.py
行业标准下载器  std.samr.gov.cn/hb

运行方式（由 process_manager 以子进程调用）：
  python -m downloaders.hangbiao

环境变量（由 process_manager 注入）：
  DOWNLOADER_SOURCE_NAME     来源名称（必填）
  DOWNLOADER_SOURCE_URL      列表页 URL（必填）
  DOWNLOADER_DOWNLOAD_DIR    下载目录（默认 download/{name}）
  DOWNLOADER_SOURCE_ID       用于 should_stop() 的唯一 ID
"""

import os
import sys
import time
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright, Page, Download

from .common import (
    BaseDownloader, DownloadRecorder, create_browser_and_context,
    save_and_rename, is_valid_pdf, remove_temp_file, finalize_temp,
    should_stop, setup_stop_signal,
)


class HangbiaoDownloader(BaseDownloader):
    """
    行业标准  std.samr.gov.cn/hb/hbQuery
    ─ 列表页 JS 翻页（Bootstrap Table AJAX），点击 › 翻页
    ─ 列表行：#, 标准号(a链接), 标准名称, 发布日期, 实施日期, 所属行业
    ─ 详情页：div.sidebar-btn.openhdbpdf（查看文本）→ 新标签 hbba.sacinfo.org.cn
    ─ hbba 页：.modal + #validate-code?pk=<hash> → #captcha-input + #download-btn
    ─ 下载：验证通过后 window.location.href=/portal/download/{token} 触发下载
    """

    def _list_page_tag(self):
        return "hbQuery"

    def _build_page_url(self, base_url: str, page_num: int) -> str:
        # 行标分页通过点击 › 实现，断点恢复从第1页开始（已记录的会跳过）
        return base_url

    def _parse_rows(self, page: Page) -> list[dict]:
        rows = []
        for tr in page.query_selector_all("table tbody tr"):
            try:
                tds = tr.query_selector_all("td")
                if len(tds) < 6:
                    continue
                std_no = tds[1].inner_text().strip()
                std_name = tds[2].inner_text().strip()
                if not std_no or not std_name:
                    continue
                a = tds[1].query_selector("a")
                href = a.get_attribute("href") if a else None
                if not href:
                    continue
                if not urlparse(href).scheme:
                    href = urljoin(page.url, href)
                rows.append(dict(std_no=std_no, std_name=std_name, detail_url=href))
            except Exception:
                continue
        return rows

    def _download_one(self, row: dict, download_dir: str, source_name: str, list_page=None) -> bool:
        std_no, std_name = row["std_no"], row["std_name"]
        detail_url = row["detail_url"]

        detail_page = None
        hbba_page = None
        try:
            # ① 打开详情页
            detail_page = self._open_page(detail_url)
            self._parse_detail_meta(detail_page, detail_url, source_name)

            # ② 检查状态，只下载现行
            if not self._is_current(detail_page):
                status_el = detail_page.query_selector("span.s-status.label-primary")
                label = status_el.inner_text().strip() if status_el else "未知"
                print(f"   ○ 状态【{label}】，非现行，跳过", flush=True)
                self.recorder.save(std_no, std_name, source_name, "ABOLISHED")
                return False

            # ③ 检查"查看文本"按钮是否存在
            open_btn = detail_page.query_selector("div.sidebar-btn.openhdbpdf")
            if not open_btn:
                print(f"   ○ 无全文（无查看文本按钮）", flush=True)
                self.recorder.save(std_no, std_name, source_name, "NO_FULL_TEXT")
                return False

            # ④⑤ 外层重试：hbba 页面失效/所有内层重试耗尽时，重新打开（最多 5 次）
            # 覆盖 window.close() 防止验证码正确后页面自毁（JS 会在1秒后调用 window.close）。
            # 使用 page.expect_download() 捕获下载，它能正确泵送 Playwright 事件循环。
            for page_attempt in range(1, 6):
                hbba_page = None
                try:
                    with self.context.expect_page(timeout=20000) as pg_info:
                        open_btn.click()
                    hbba_page = pg_info.value
                    try:
                        hbba_page.wait_for_load_state("domcontentloaded", timeout=15000)
                    except Exception:
                        pass
                    time.sleep(2)

                    # 阻止 hbba 页面自关闭（JS 验证码正确后 1 秒调用 window.close）
                    hbba_page.evaluate("() => { window.close = () => {} }")

                    dl = self._solve_captcha(hbba_page)
                    if dl:
                        saved = save_and_rename(dl, download_dir, std_no, std_name)
                        if not is_valid_pdf(saved):
                            print(f"   ✗ 下载文件不是有效 PDF，跳过", flush=True)
                            remove_temp_file(saved)
                            continue  # 外层重试，重新打开 hbba 页
                        result = finalize_temp(saved, download_dir, "hangbiao")
                        self.recorder.save(std_no, std_name, source_name, "SUCCESS",
                                           oss_url=result.get("oss_url"),
                                           oss_path=result.get("oss_path"),
                                           local_path=result.get("local_path"))
                        return True

                except Exception as e:
                    print(f"   ⚠ 打开 hbba 页失败：{e}", flush=True)
                finally:
                    self._close_pages(hbba_page)

                if page_attempt < 5:
                    print(f"   ↺ 验证码失效，重新打开（{page_attempt}/5）...", flush=True)
                    try:
                        open_btn = detail_page.query_selector("div.sidebar-btn.openhdbpdf")
                        if not open_btn:
                            print(f"   ⚠ 详情页已失效，放弃", flush=True)
                            return False
                    except Exception:
                        print(f"   ⚠ 详情页已失效，放弃", flush=True)
                        return False
                    time.sleep(2)

            # 所有重试耗尽仍未下载成功，记录为无全文
            print(f"   ✗ 验证码重试全部失败，标记为无全文", flush=True)
            self.recorder.save(std_no, std_name, source_name, "NO_FULL_TEXT")
            return False

        finally:
            self._close_pages(detail_page)

    def _parse_detail_meta(self, page: Page, detail_url: str, source_name: str) -> None:
        """
        解析行标详情页元数据并写入 MySQL。
        异常时打印警告并静默跳过，不影响下载主流程。
        """
        try:
            from .db import upsert_hangbiao_detail, upsert_hangbiao_replace_stds

            # ── 标准名称（h4）────────────────────────────────────────
            h4 = page.query_selector("h4")
            std_name = h4.inner_text().strip() if h4 else ""

            # ── 顶部标签区（行业代码 / 强制性 / 状态）──────────────
            tag_info = page.evaluate("""() => {
                const r = {industry: '', mandatory: '', status: ''};
                document.querySelectorAll('span').forEach(el => {
                    const t = el.textContent.trim();
                    if (t.startsWith('行业标准-') && t.length < 40)
                        r.industry = t.replace('行业标准-', '').trim();
                    else if (['强制性', '推荐性', '指导性'].includes(t))
                        r.mandatory = t;
                    else if (['现行', '废止', '即将实施', '制定中'].includes(t))
                        r.status = t;
                });
                return r;
            }""")
            industry_str   = tag_info.get("industry", "")
            mandatory_type = tag_info.get("mandatory", "")
            status         = tag_info.get("status", "")

            # 行业代码 / 行业名称："AQ 安全生产" → code="AQ", name="安全生产"
            parts = industry_str.split(" ", 1)
            industry_code = parts[0]
            industry_name = parts[1] if len(parts) > 1 else ""

            # ── 基础信息 dt/dd 键值对 ────────────────────────────────
            fields: dict = {}
            for dl in page.query_selector_all("dl"):
                dts = dl.query_selector_all("dt")
                dds = dl.query_selector_all("dd")
                for dt, dd in zip(dts, dds):
                    key = dt.inner_text().strip()
                    val = dd.inner_text().strip()
                    if key:
                        fields[key] = val

            # ── 废止日期（状态时间线）────────────────────────────────
            abolish_date = None
            for a in page.query_selector_all("ul li a"):
                txt = a.inner_text().strip()
                if "废止于" in txt:
                    abolish_date = txt.replace("废止于", "").strip() or None
                    break

            # ── 适用范围 / 起草单位 / 起草人 / 备案信息（paragraph 文本）──
            record_no = record_notice = ""
            scope = drafting_orgs = drafting_persons = ""
            for p in page.query_selector_all("p"):
                txt = p.inner_text().strip()
                if txt.startswith("备案号："):
                    record_no = txt[len("备案号："):].rstrip("。").strip()
                elif txt.startswith("备案公告："):
                    record_notice = txt[len("备案公告："):].rstrip("。").strip()
                elif txt.startswith("主要起草单位"):
                    drafting_orgs = txt[len("主要起草单位"):].strip().rstrip("。").strip()
                elif txt.startswith("主要起草人"):
                    drafting_persons = txt[len("主要起草人"):].strip().rstrip("。").strip()

            # 适用范围：取"适用范围"标题后的第一个 <p>
            scope = page.evaluate("""() => {
                const h2 = Array.from(document.querySelectorAll('h2'))
                              .find(h => h.textContent.trim() === '适用范围');
                if (!h2) return '';
                let el = h2.nextElementSibling;
                while (el && el.tagName !== 'H2') {
                    if (el.tagName === 'P') return el.textContent.trim();
                    el = el.nextElementSibling;
                }
                return '';
            }""")

            std_no = fields.get("标准号", "").strip()
            if not std_no:
                return

            meta = {
                "std_no":            std_no,
                "std_name":          std_name,
                "industry_code":     industry_code,
                "industry_name":     industry_name,
                "mandatory_type":    mandatory_type,
                "status":            status,
                "publish_date":      fields.get("发布日期") or None,
                "implement_date":    fields.get("实施日期") or None,
                "abolish_date":      abolish_date,
                "ccs":               fields.get("中国标准分类号") or None,
                "ics":               fields.get("国际标准分类号") or None,
                "org_unit":          fields.get("归口单位") or None,
                "department":        fields.get("主管部门") or None,
                "industry_category": fields.get("行业分类") or None,
                "scope":             scope or None,
                "drafting_orgs":     drafting_orgs or None,
                "drafting_persons":  drafting_persons or None,
                "record_no":         record_no or None,
                "record_notice":     record_notice or None,
                "detail_url":        detail_url,
                "source_name":       source_name,
            }
            upsert_hangbiao_detail(meta)

            # ── 被代替标准关联表 ─────────────────────────────────────
            replace_str = fields.get("全部代替标准", "")
            if replace_str:
                replaced = [
                    s.strip()
                    for s in replace_str.replace("，", ",").split(",")
                    if s.strip()
                ]
                upsert_hangbiao_replace_stds(std_no, replaced)

        except Exception as e:
            print(f"   ⚠ 元数据解析失败：{e}", flush=True)

    def _is_current(self, page: Page) -> bool:
        el = page.query_selector("span.s-status.label-primary")
        if not el:
            return True  # 找不到标签时保守处理，尝试下载
        return el.inner_text().strip() == "现行"

    def _solve_captcha(self, page: Page, max_retries: int = 5):
        """
        行标验证码：hbba 页面 .modal + validate-code?pk=<hash>
        验证通过后 JS 做 AJAX 校验 → window.location.href 跳转下载 URL。

        核心机制：用 page.route 拦截 /portal/download/ 请求，
        强制添加 Content-Disposition: attachment 头，
        使 Playwright 将其识别为文件下载而非普通导航，
        从而让 expect_download 能正确捕获 download 事件。

        Returns: Download 对象（成功）或 None（失败）
        """
        try:
            page.wait_for_selector(".modal", timeout=10000)
            time.sleep(1.5)
        except Exception as e:
            print(f"   ⚠ 等待验证码弹窗超时：{e}", flush=True)
            return None

        # 拦截 /portal/download/ 请求，强制 Content-Disposition 头触发下载事件
        page.route('**/portal/download/**', self._force_download_route)

        try:
            return self._captcha_loop(page, max_retries)
        finally:
            try:
                page.unroute('**/portal/download/**')
            except Exception:
                pass

    def _captcha_loop(self, page: Page, max_retries: int):
        """验证码识别-提交-重试循环（从 _solve_captcha 中拆出以配合 route finally）。"""
        for attempt in range(1, max_retries + 1):
            time.sleep(1)
            try:
                # ── 诊断：每次尝试前打印页面状态 ──
                diag = self._page_diag(page)
                print(f"   [diag#{attempt}] url={diag['url'][:60]}  modal={diag['modal']}"
                      f"  img={diag['img']}  inp={diag['inp']}  btn={diag['btn']}"
                      f"  layers={diag['layers']}  closed={diag['closed']}", flush=True)

                try:
                    img_el = page.wait_for_selector("#validate-code", timeout=5000)
                except Exception:
                    img_el = None
                if not img_el:
                    raise ValueError("未找到验证码图片 #validate-code")

                img_bytes = img_el.screenshot()
                code = self._ocr(img_bytes)
                if len(code) != 4:
                    raise ValueError(f"识别结果长度不对：{code!r}")

                print(f"   [{attempt}/{max_retries}] 行标验证码：{code}", flush=True)

                inp = page.query_selector("#captcha-input")
                if not inp:
                    raise ValueError("未找到验证码输入框 #captcha-input")
                inp.fill(code)

                dl_btn = page.query_selector("#download-btn")
                if not dl_btn:
                    raise ValueError("未找到'下载标准'按钮 #download-btn")

                # expect_download 捕获下载事件（15s 留足 AJAX + 导航时间）：
                # - 验证码正确：AJAX → window.location.href → route 拦截加头 → download 事件
                # - 验证码错误：AJAX 返回错误 → 无导航 → 超时
                try:
                    with page.expect_download(timeout=15000) as dl_info:
                        dl_btn.click()
                    dl = dl_info.value
                    print("   ✓ 行标下载已触发", flush=True)
                    return dl
                except Exception as ed:
                    # ── 诊断：expect_download 超时后立即打印页面状态 ──
                    diag2 = self._page_diag(page)
                    print(f"   [diag-timeout#{attempt}] err={type(ed).__name__}"
                          f"  url={diag2['url'][:60]}  modal={diag2['modal']}"
                          f"  img={diag2['img']}  closed={diag2['closed']}", flush=True)

                    # 页面已跳转到空白下载页（验证码错误或 token 无效），
                    # 内层刷新重试无意义，退出让外层重新从详情页打开 hbba 页
                    if '/portal/download/' in diag2.get('url', '') or '/portal/download/' in page.url:
                        print("   ⚠ 页面已跳转到空白下载页，退出内层重试", flush=True)
                        return None

                if attempt < max_retries:
                    print("   ⚠ 验证码错误，刷新重试...", flush=True)
                    try:
                        self._dismiss_layer(page)
                        self._refresh_captcha(page)
                        inp2 = page.query_selector("#captcha-input")
                        if inp2:
                            inp2.fill("")
                    except Exception:
                        print("   ⚠ hbba 页面已失效，停止重试", flush=True)
                        return None
                    continue

            except Exception as e:
                if attempt < max_retries:
                    print(f"   ⚠ 识别出错({e})，刷新重试...", flush=True)
                    try:
                        self._dismiss_layer(page)
                        self._refresh_captcha(page)
                    except Exception:
                        print("   ⚠ hbba 页面已失效，停止重试", flush=True)
                        return None
                else:
                    print(f"   ⚠ 行标验证码识别失败：{e}", flush=True)
                    return None
        return None

    @staticmethod
    def _force_download_route(route):
        """拦截 /portal/download/ 导航请求，强制添加 Content-Disposition 头。

        行标网站验证码正确后 JS 做 window.location.href 跳转到 /portal/download/{token}，
        服务端返回 PDF 但可能不带 Content-Disposition: attachment 头，
        导致 Playwright 视为普通页面导航而非文件下载，expect_download 永远捕获不到事件。
        通过 route 拦截并强制加上该头，Playwright 即可正常触发 download 事件。
        """
        try:
            resp = route.fetch()
            headers = dict(resp.headers)
            has_cd = any(k.lower() == 'content-disposition' for k in headers)
            if not has_cd:
                headers['content-disposition'] = 'attachment; filename="standard.pdf"'
            route.fulfill(status=resp.status, headers=headers, body=resp.body())
        except Exception:
            route.abort()

    @staticmethod
    def _retry_download(page: Page):
        """
        验证码正确后页面已跳转到 /portal/download/{token}，
        但 expect_download 未捕获到下载事件。
        尝试方案：reload 当前下载 URL 重新触发下载。
        """
        try:
            dl_url = page.evaluate('() => location.href')
        except Exception:
            dl_url = page.url
        for i in range(3):
            try:
                with page.expect_download(timeout=15000) as dl_info:
                    page.goto(dl_url)
                dl = dl_info.value
                print(f"   ✓ 行标下载已触发(重试{i+1})", flush=True)
                return dl
            except Exception:
                print(f"   ⚠ 重新下载尝试{i+1}失败", flush=True)
                time.sleep(1)
        return None

    @staticmethod
    def _page_diag(page: Page) -> dict:
        """收集 hbba 页面关键元素状态，用于诊断验证码消失问题。"""
        try:
            return page.evaluate("""() => {
                const img = document.querySelector('#validate-code');
                return {
                    url: location.href,
                    modal: !!document.querySelector('.modal'),
                    img: img ? ('ok src=' + (img.src || '').slice(-30)) : 'MISSING',
                    inp: !!document.querySelector('#captcha-input'),
                    btn: !!document.querySelector('#download-btn'),
                    layers: document.querySelectorAll('.layui-layer').length,
                    closed: typeof window.__closed !== 'undefined',
                    childCount: document.body.children.length,
                };
            }""")
        except Exception as e:
            return {"url": "ERR", "modal": False, "img": f"ERR:{e}",
                    "inp": False, "btn": False, "layers": -1,
                    "closed": "ERR", "childCount": -1}

    @staticmethod
    def _dismiss_layer(page: Page):
        """移除 layui layer.msg 弹层，防止其在 headless 下干扰后续 DOM 查询。"""
        try:
            page.evaluate(
                "() => document.querySelectorAll('.layui-layer, .layui-layer-shade').forEach(el => el.remove())"
            )
        except Exception:
            pass

    def _refresh_captcha(self, page: Page):
        """点击刷新按钮并等待新验证码图片加载完成。"""
        refresh = page.query_selector(".fa-refresh")
        if refresh:
            refresh.click()
        else:
            img = page.query_selector("#validate-code")
            if img:
                try:
                    img.click()
                except Exception:
                    pass
        # 等待新验证码图片加载（src 带时间戳参数会变化）
        try:
            page.wait_for_selector("#validate-code", state="attached", timeout=5000)
            time.sleep(1)
        except Exception:
            time.sleep(2)

    def _go_next_page(self, page: Page) -> bool:
        # 等待 Bootstrap Table 加载遮罩消失后再操作分页
        try:
            page.wait_for_selector(
                "div.fixed-table-loading", state="hidden", timeout=15000
            )
        except Exception:
            pass

        next_btn = None
        for a in page.query_selector_all("ul.pagination a, .pagination a"):
            if a.inner_text().strip() == "›":
                next_btn = a
                break
        if not next_btn:
            return False
        par_cls = next_btn.evaluate("el => el.parentElement?.className || ''")
        if "disabled" in par_cls:
            return False
        next_btn.click()
        print("   → 翻页...", flush=True)
        # 等待加载遮罩出现再消失，确保新数据渲染完成
        try:
            page.wait_for_selector(
                "div.fixed-table-loading", state="hidden", timeout=15000
            )
        except Exception:
            pass
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

    print(f"[行标] 来源：{source_name}", flush=True)
    print(f"[行标] URL：{source_url}", flush=True)
    print(f"[行标] 下载目录：{download_dir}", flush=True)

    source = {
        "name": source_name,
        "type": "hangbiao",
        "url": source_url,
        "download_dir": download_dir,
    }
    recorder = DownloadRecorder(source_type="hangbiao")
    recorder.load_from_db(source_name)

    with sync_playwright() as pw:
        browser, context = create_browser_and_context(pw)
        list_page = context.new_page()
        try:
            HangbiaoDownloader(context, recorder, source_id).download_source(source, list_page)
        finally:
            print("\n🎉 行标下载任务完成", flush=True)
            browser.close()


if __name__ == "__main__":
    main()
