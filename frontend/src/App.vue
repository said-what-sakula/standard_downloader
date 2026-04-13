<template>
  <a-layout style="min-height: 100vh">
    <!-- 侧边导航 -->
    <a-layout-sider width="200" theme="dark">
      <div class="logo">📥 标准下载平台</div>
      <a-menu
        v-model:selectedKeys="selectedKeys"
        theme="dark"
        mode="inline"
        @click="onMenuClick"
      >
        <a-menu-item key="/records">
          <template #icon><database-outlined /></template>
          标准库
        </a-menu-item>
        <a-menu-item key="/dashboard">
          <template #icon><dashboard-outlined /></template>
          控制台
        </a-menu-item>
        <a-menu-item key="/logs">
          <template #icon><file-text-outlined /></template>
          实时日志
        </a-menu-item>
        <a-menu-item key="/schedule">
          <template #icon><clock-circle-outlined /></template>
          定时增量
        </a-menu-item>
        <a-menu-item key="/config">
          <template #icon><setting-outlined /></template>
          配置管理
        </a-menu-item>
      </a-menu>
    </a-layout-sider>

    <!-- 主内容区 -->
    <a-layout>
      <a-layout-content style="margin: 24px 16px; padding: 24px; background: #fff; border-radius: 8px;">
        <router-view />
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  DashboardOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  ClockCircleOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'

const router = useRouter()
const route  = useRoute()
const selectedKeys = ref([route.path])

watch(() => route.path, (p) => { selectedKeys.value = [p] })

function onMenuClick({ key }: { key: string }) {
  router.push(key)
}
</script>

<style>
* { box-sizing: border-box; }
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
.logo {
  color: #fff;
  font-size: 14px;
  font-weight: bold;
  padding: 16px;
  text-align: center;
  border-bottom: 1px solid rgba(255,255,255,.1);
}
</style>
