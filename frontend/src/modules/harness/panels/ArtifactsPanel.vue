<script setup>
import { inject } from 'vue'
import { HARNESS_SHELL } from '../context'
import ArtifactList from '../../artifacts/ArtifactList.vue'

const ctxShell = inject(HARNESS_SHELL)

const { activeSection, props } = ctxShell
</script>

<template>



        <section v-if="activeSection === 'artifacts'" class="resource-page">
          <section class="harness-panel resource-table-panel"><ArtifactList :api-base="props.apiBase" /></section>

        </section>



</template>
