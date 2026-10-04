<template>
  <div class="wall">
    <h1 class="serif">
      {{ editing ? '' : w.title }}
      <button v-if="!editing" class="ghost mini" @click="startEdit">改标题</button>
    </h1>
    <input v-if="editing" v-model="draftTitle" @keyup.enter="saveTitle" placeholder="标题" />
    <button v-if="editing" @click="saveTitle">保存</button>
    <button v-if="editing" class="ghost" @click="editing=false">取消</button>
    <p>{{ w.note }}</p>
    <p class="tag">
      状态 {{ w.status_text }}<template v-if="w.countdown_text"> · {{ w.countdown_text }}</template>
      · 认领人 {{ w.claimer || '—' }}
    </p>
    <p v-if="err" class="err">{{ err }}</p>
    <input v-model="claimer" placeholder="你的名字" />
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <button :disabled="!w.claimable" @click="claim">认领锁定</button>
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
const claimer = ref('访客')
const err = ref('')
const editing = ref(false)
const draftTitle = ref('')
async function load() { w.value = await api('/wishes/' + props.id) }
function startEdit() { draftTitle.value = w.value.title || ''; editing.value = true }
async function saveTitle() {
  err.value = ''
  try {
    await api('/wishes/' + props.id, { method: 'PATCH', body: JSON.stringify({ title: draftTitle.value }) })
    editing.value = false; await load()
  } catch (e) { err.value = e.message }
}
async function claim() {
  err.value=''; try { await api('/wishes/'+props.id+'/claim',{method:'POST',body:JSON.stringify({claimer:claimer.value})}); await load() } catch(e){ err.value=e.message }
}
async function release() {
  err.value=''; try { await api('/wishes/'+props.id+'/release',{method:'POST',body:'{}'}); await load() } catch(e){ err.value=e.message }
}
async function fulfill() {
  err.value=''; try { await api('/wishes/'+props.id+'/fulfill',{method:'POST',body:'{}'}); await load() } catch(e){ err.value=e.message }
}
onMounted(load)
</script>
