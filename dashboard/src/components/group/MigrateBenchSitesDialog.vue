<script setup lang="ts">
import { Button, Checkbox, createResource, Dialog } from 'frappe-ui'
import { computed, h, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import { getToastErrorMessage } from '../../utils/toast'
import GenericList from '../GenericList.vue'

type SiteRow = { name: string; skip_failing_patches: boolean; disabled: boolean }
type SiteData = { name: string; fatal_site_update: string | null }

const props = defineProps<{ bench: string; releaseGroup: string }>()

const show = ref(true)
const router = useRouter()
const selected = ref<string[]>([])
const rows = reactive<SiteRow[]>([])

const sites = createResource({
	url: 'press.api.client.get_list',
	params: {
		doctype: 'Site',
		fields: ['name', 'fatal_site_update'],
		filters: { bench: props.bench, status: 'Active' },
		order_by: 'name asc',
		// press.api.client.get_list returns 20 rows unless given a limit
		limit: 1000,
	},
	auto: true,
	onSuccess: (data: SiteData[]) =>
		rows.splice(
			0,
			rows.length,
			// A site blocked by a failed update cannot migrate, so it stays visible but unselectable
			...data.map((site) => ({
				name: site.name,
				skip_failing_patches: false,
				disabled: !!site.fatal_site_update,
			})),
		),
})

const migrate = createResource({ url: 'press.api.client.run_doc_method' })

const listOptions = computed(() => ({
	data: rows,
	selectable: true,
	columns: [
		{ label: 'Site', fieldname: 'name' },
		{
			label: 'Status',
			fieldname: 'disabled',
			width: 0.6,
			type: 'Component',
			component: ({ row }: { row: SiteRow }) =>
				row.disabled
					? h(
							'span',
							{
								class: 'text-sm text-ink-red-4',
								title: 'Resolve the failed update first',
							},
							'Blocked: failed update',
						)
					: null,
		},
		{
			label: 'Skip failed patches',
			fieldname: 'skip_failing_patches',
			width: 0.5,
			type: 'Component',
			component: ({ row }: { row: SiteRow }) =>
				h(Checkbox, {
					modelValue: row.skip_failing_patches,
					disabled: row.disabled,
					'onUpdate:modelValue': (value: boolean) => {
						row.skip_failing_patches = value
					},
				}),
		},
	],
}))

function migrateSelected() {
	const chosen = rows.filter((row) => selected.value.includes(row.name))
	const request = migrate.submit({
		dt: 'Bench',
		dn: props.bench,
		method: 'migrate_sites',
		args: { sites: chosen },
	})
	toast.promise(request, {
		loading: `Starting migration for ${chosen.length} sites...`,
		success: () => {
			show.value = false
			router.push({
				name: 'Release Group Detail Jobs',
				params: { name: props.releaseGroup },
			})
			return `Migration started for ${chosen.length} sites`
		},
		error: (e: unknown) => getToastErrorMessage(e, 'Failed to start the migration'),
	})
}
</script>

<template>
	<Dialog v-model="show" :options="{ title: 'Migrate Sites', size: '3xl' }">
		<template #body-content>
			<h2 class="mb-4 text-lg font-medium">Select sites to migrate</h2>
			<GenericList
				v-if="rows.length"
				class="max-h-[500px]"
				:options="listOptions"
				@update:selections="
					(names: Set<string>) => (selected = Array.from(names))
				"
			/>
			<p
				v-else-if="!sites.loading"
				class="text-center text-base font-medium text-ink-gray-6"
			>
				No active sites on this bench
			</p>
		</template>
		<template #actions>
			<div class="flex justify-between">
				<Button label="Back" @click="show = false" />
				<Button
					variant="solid"
					label="Migrate"
					:disabled="!selected.length"
					:loading="migrate.loading"
					@click="migrateSelected"
				/>
			</div>
		</template>
	</Dialog>
</template>
