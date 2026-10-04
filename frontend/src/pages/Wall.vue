<template>
  <div class="wall">
    <h1 class="serif">愿望墙</h1>
    <p class="tag">无顶栏 · 瀑布流 · 点卡片认领</p>
    <div class="masonry">
      <article v-for="w in rows" :key="w.id" class="card" @click="$router.push('/wishes/'+w.id)">
        <span class="badge" :class="{ open: w.claimable }">{{ w.badge }}</span>
        <h3>{{ w.display_title }}</h3>
        <p>{{ w.note }}</p>
        <span class="tag">{{ w.status_text }}<template v-if="w.countdown_text"> · {{ w.countdown_text }}</template></span>
      </article>
    </div>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
const rows = ref([])
onMounted(async () => { rows.value = await api('/wishes') })
</script>
