<template>
  <div class="wall">
    <h1 class="serif">{{ w.display_title }}</h1>
    <p>{{ w.note }}</p>
    <p class="tag">状态 {{ w.status_text }}<template v-if="w.countdown_text"> · {{ w.countdown_text }}</template> · 认领人 {{ w.claimer || '—' }}</p>
    <p v-if="err" class="err">{{ err }}</p>
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <input v-model="title" placeholder="标题" />
      <button class="ghost" @click="rename">改标题</button>
    </div>
    <input v-model="claimer" placeholder="你的名字" />
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <button @click="claim">认领锁定</button>
      <button class="ghost" @click="release">释放</button>
      <button class="ghost" @click="fulfill">核销完成</button>
    </div>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
const props = defineProps({ id: String })
const w = ref({})
const title = ref('')
const claimer = ref('访客')
const err = ref('')
async function load() {
  w.value = await api('/wishes/' + props.id)
  title.value = w.value.title || ''
}
async function rename() {
  err.value = ''
  try { w.value = await api('/wishes/' + props.id, { method: 'PATCH', body: JSON.stringify({ title: title.value }) }) }
  catch (e) { err.value = e.message }
}
async function claim() {
  err.value=''; try { w.value = await api('/wishes/'+props.id+'/claim',{method:'POST',body:JSON.stringify({claimer:claimer.value})}) } catch(e){ err.value=e.message }
}
async function release() {
  err.value=''; try { w.value = await api('/wishes/'+props.id+'/release',{method:'POST',body:'{}'}) } catch(e){ err.value=e.message }
}
async function fulfill() {
  err.value=''; try { w.value = await api('/wishes/'+props.id+'/fulfill',{method:'POST',body:'{}'}) } catch(e){ err.value=e.message }
}
onMounted(load)
</script>
