<script setup lang="ts">
import {
	Badge,
	Button,
	Combobox,
	Select,
	Spinner,
	TextInput,
	Tooltip,
	createResource,
} from 'frappe-ui'
import { computed, ref } from 'vue'
import Scrollbar from '@/components/common/Scrollbar.vue'
import Header from '@/components/Header.vue'
import { bytes, date } from '@/utils/format'
import { getSiteStatusBadge } from '@/utils/site'

const periodOptions = ['Today', 'Yesterday', 'Last 24 Hours', 'Last 7 Days']
const statusOptions = ['All', 'Missing', 'Failed', 'In Progress', 'Backed Up']

// Sites that need attention sort to the top
const statusOrder = ['Missing', 'Failed', 'In Progress', 'Backed Up']
const statusTheme: Record<string, string> = {
	Missing: 'red',
	Failed: 'red',
	'In Progress': 'blue',
	'Backed Up': 'green',
}

const period = ref('Today')
const status = ref('All')
const server = ref('')
const search = ref('')

const backups = createResource({
	url: 'press.api.backup_monitor.get_site_backups',
	makeParams: () => ({ period: period.value }),
	auto: true,
})

const rows = computed(() => backups.data || [])

const serverOptions = computed(() =>
	[...new Set(rows.value.map((row: any) => row.server))].sort(),
)

const filteredRows = computed(() =>
	rows.value
		.filter((row: any) => status.value === 'All' || row.backup_status === status.value)
		.filter((row: any) => !server.value || row.server === server.value)
		.filter((row: any) => row.host_name.includes(search.value.trim().toLowerCase()))
		.sort(
			(a: any, b: any) =>
				statusOrder.indexOf(a.backup_status) - statusOrder.indexOf(b.backup_status),
		),
)

const countByStatus = (value: string) =>
	rows.value.filter((row: any) => row.backup_status === value).length

const changePeriod = (value: string) => {
	period.value = value
	backups.reload()
}
</script>

<template>
	<div class="flex flex-col h-dvh">
		<Header class="bg-surface-white shrink-0">
			<Breadcrumbs :items="[{ label: 'Backup Monitor', route: '/backup-monitor' }]" />
			<Button class="ml-auto" :loading="backups.loading" @click="backups.reload()">
				<template #icon><lucide-refresh-ccw class="size-4" /></template>
			</Button>
		</Header>

		<div class="flex flex-wrap gap-3 px-5 pt-4 text-sm">
			<div class="rounded border px-3 py-2">
				<span class="font-medium text-ink-gray-8">
					{{ countByStatus('Backed Up') }} of {{ rows.length }}
				</span>
				<span class="text-ink-gray-5"> sites backed up · {{ period.toLowerCase() }}</span>
			</div>
			<button
				v-for="value in ['Missing', 'Failed', 'In Progress']"
				:key="value"
				class="rounded border px-3 py-2 hover:bg-surface-gray-2"
				@click="status = value"
			>
				<span class="font-medium" :class="countByStatus(value) && value !== 'In Progress' ? 'text-ink-red-4' : 'text-ink-gray-8'">
					{{ countByStatus(value) }}
				</span>
				<span class="text-ink-gray-5"> {{ value.toLowerCase() }}</span>
			</button>
		</div>

		<div class="flex items-center gap-2 px-5 py-3 overflow-auto">
			<TextInput v-model="search" placeholder="Search sites" class="w-56 shrink-0">
				<template #prefix><lucide-search class="size-4 text-ink-gray-5" /></template>
			</TextInput>
			<Select
				class="!w-40 shrink-0"
				:options="periodOptions"
				:modelValue="period"
				@update:modelValue="changePeriod"
			/>
			<Select v-model="status" class="!w-36 shrink-0" :options="statusOptions" />
			<Combobox
				v-model="server"
				placeholder="Server"
				class="!w-56 shrink-0"
				:openOnFocus="true"
				:options="serverOptions"
			>
				<template #prefix><LucideServer class="size-4 text-ink-gray-5" /></template>
			</Combobox>
		</div>

		<Scrollbar class="flex-1 min-h-0 px-5">
			<table class="backups-table w-full">
				<thead class="text-ink-gray-5 text-sm">
					<tr>
						<th class="rounded-l">Site</th>
						<th>Site Status</th>
						<th>Backup</th>
						<th>Last Successful Backup</th>
						<th>Offsite</th>
						<th>Size</th>
						<th>Backups</th>
						<th class="rounded-r">Server</th>
					</tr>
				</thead>

				<tbody class="text-ink-gray-8">
					<tr v-if="backups.loading && !rows.length">
						<td colspan="8">
							<div class="flex items-center justify-center py-20">
								<Spinner class="size-5" />
							</div>
						</td>
					</tr>

					<tr v-for="row in filteredRows" :key="row.site" class="*:border-b">
						<td class="font-medium">
							<Tooltip text="Go to the site's backups">
								<router-link
									class="hover:underline"
									:to="{ name: 'Site Detail Backups', params: { name: row.site } }"
								>
									{{ row.host_name }}
								</router-link>
							</Tooltip>
						</td>
						<td>
							<Badge variant="subtle" :theme="getSiteStatusBadge(row.site_status).theme">
								{{ row.site_status }}
							</Badge>
						</td>
						<td>
							<Badge variant="subtle" :theme="statusTheme[row.backup_status]">
								{{ row.backup_status }}
							</Badge>
						</td>
						<td>{{ row.last_success_on ? date(row.last_success_on, 'lll') : '–' }}</td>
						<td>{{ row.last_success_on ? (row.offsite ? 'Yes' : 'No') : '–' }}</td>
						<td>{{ row.size ? bytes(row.size) : '–' }}</td>
						<td>{{ row.successful }} / {{ row.backups }}</td>
						<td class="text-ink-gray-5">{{ row.server }}</td>
					</tr>
				</tbody>
			</table>

			<div
				v-if="!backups.loading && !filteredRows.length"
				class="py-10 text-center text-sm text-ink-gray-5"
			>
				No sites
			</div>
		</Scrollbar>

		<div class="shrink-0 px-5 py-2 flex justify-end">
			<span class="text-sm text-ink-gray-5">
				Showing {{ filteredRows.length }} of {{ rows.length }} sites
			</span>
		</div>
	</div>
</template>

<style scoped>
.backups-table th {
	@apply p-2 sticky top-0 z-10 bg-surface-gray-1 text-left font-normal;
}

.backups-table td {
	@apply p-2 whitespace-nowrap;
}
</style>
