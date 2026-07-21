<template>
	<Dialog v-if="show" :options="{ title, position: 'top' }" v-model="show">
		<template v-slot:body-content>
			<div class="flex flex-col gap-4">
				<p class="text-base text-ink-gray-6">
					You can select the app patch by either entering the patch URL, or by
					selecting a patch file.
				</p>
				<div class="flex flex-col gap-2">
					<FormControl
						v-if="!app"
						class="w-full"
						v-model="applyToApp"
						label="Select app"
						placeholder="Select app to patch"
						type="select"
						variant="outline"
						:options="appOptions"
					/>

					<!-- From / To commit selector -->
					<div v-if="commitOptions.length > 1" class="flex flex-col gap-2">
						<div class="grid grid-cols-2 gap-2">
							<FormControl
								label="From"
								type="select"
								variant="outline"
								v-model="fromHash"
								:options="commitOptions"
							/>
							<FormControl
								label="To"
								type="select"
								variant="outline"
								v-model="toHash"
								:options="commitOptions"
							/>
						</div>
						<div v-if="fromHash && toHash" class="flex gap-2">
							<Button
								class="flex-1"
								label="View compare"
								@click="openCompare(false)"
							>
								<template #prefix>
									<FeatherIcon name="external-link" class="h-4 w-4" />
								</template>
							</Button>
							<Button
								class="flex-1"
								label="View .patch"
								@click="openCompare(true)"
							>
								<template #prefix>
									<FeatherIcon name="external-link" class="h-4 w-4" />
								</template>
							</Button>
						</div>
					</div>

					<!-- Patch Selector (URL or File) -->
					<div class="flex w-full items-end gap-1">
						<FormControl
							v-if="!patch"
							class="w-full"
							label="Patch URL"
							type="data"
							v-model="patchURL"
							variant="outline"
							placeholder="Enter patch URL"
						/>
						<FormControl
							v-else
							class="w-full"
							label="Patch File Name"
							type="data"
							variant="outline"
							v-model="patchFileName"
							placeholder="Set patch file name"
						/>

						<!-- File Selector -->
						<input
							ref="fileSelector"
							type="file"
							:accept="['text/x-patch', 'text/x-diff', 'application/x-patch']"
							class="hidden"
							@change="onPatchFileSelect"
						/>
						<Button
							@click="$refs.fileSelector.click()"
							title="Select patch file"
						>
							<FeatherIcon name="file-text" class="h-5 w-5 text-ink-gray-6" />
						</Button>

						<!-- Clear Patch File -->
						<Button @click="clear" v-if="patch" title="Clear patch file">
							<FeatherIcon name="x" class="h-5 w-5 text-ink-gray-6" />
						</Button>
					</div>
				</div>
				<ErrorMessage class="-mt-2 w-full" :message="error" />
				<h3 class="mt-4 text-base font-semibold">Patch Config</h3>
				<FormControl
					v-if="!applyToAllBenches && !applyToLatestDeploy"
					v-model="applyToBench"
					label="Select bench"
					type="select"
					variant="outline"
					:options="benchList"
				/>
				<FormControl
					v-if="!applyToLatestDeploy"
					label="Apply patch to all active benches"
					type="checkbox"
					v-model="applyToAllBenches"
				/>
				<FormControl
					v-if="!applyToAllBenches"
					label="Apply patch to all active benches from the latest deploy"
					type="checkbox"
					v-model="applyToLatestDeploy"
				/>
				<FormControl
					label="Build assets after applying patch"
					type="checkbox"
					v-model="buildAssets"
				/>
			</div>
		</template>
		<template v-slot:actions>
			<Button
				variant="solid"
				class="w-full"
				@click="applyPatch"
				:loading="applying"
			>
				Apply Patch
			</Button>
		</template>
	</Dialog>
</template>
<script>
import {
	Button,
	call,
	Dialog,
	ErrorMessage,
	FeatherIcon,
	FileUploader,
	FormControl,
} from 'frappe-ui';

export default {
	name: 'PatchAppDialog',
	props: {
		app: [null, String],
		group: String,
	},
	components: {
		Dialog,
		FormControl,
		ErrorMessage,
		FileUploader,
		Button,
		FeatherIcon,
	},
	watch: {
		app(value) {
			this.show = !!value;
			this.applyToApp = value || '';
		},
		show(value) {
			this.error = '';
			if (value) {
				return;
			}

			setTimeout(this.clearApp, 150);
		},
		selectedApp() {
			// Reset the from/to selection and default From to the current commit,
			// then upgrade it to the last patched commit if there is one.
			this.lastPatchHead = '';
			this.fromHash = this.selectedAppInfo?.current_hash || '';
			this.toHash = '';
			this.fetchLastPatchHead();
		},
		comparePatchUrl(value) {
			// Keep the Patch URL in sync with the selected commit range
			if (value) {
				this.patchURL = value;
			}
		},
	},
	data() {
		return {
			show: true,
			error: '',
			patch: '',
			patchURL: '',
			patchFileName: '',
			buildAssets: false,
			applyToApp: '',
			fromHash: '',
			toHash: '',
			applyToBench: '',
			applyToAllBenches: false,
			applyToLatestDeploy: false,
			deployApps: [],
			benchList: [],
			applying: false,
			lastPatchHead: '',
		};
	},
	created() {
		this.fetchApps();
		this.fetchBenches();
	},
	computed: {
		title() {
			const app = this.app || this.applyToApp;
			if (app) {
				return `Apply a patch to ${app}`;
			}

			return 'Apply a patch';
		},
		selectedApp() {
			return this.app || this.applyToApp;
		},
		appOptions() {
			return this.deployApps.map((app) => ({
				value: app.app,
				label: app.title || app.app,
			}));
		},
		selectedAppInfo() {
			const apps = this.deployApps;
			const key = this.selectedApp;
			// The selected identifier may be the app name, title, or source
			// depending on where the dialog was opened from, so match on any.
			return (
				apps.find(
					(app) =>
						app.name === key || app.app === key || app.title === key,
				) || null
			);
		},
		commitOptions() {
			const app = this.selectedAppInfo;
			if (!app) {
				return [];
			}

			const options = [{ label: 'Select commit', value: '' }];
			if (app.current_hash) {
				options.push({
					label: `Current (${app.current_hash.slice(0, 7)})`,
					value: app.current_hash,
				});
			}

			// deploy_information returns releases newest-first; show them oldest-first
			// (chronological, like GitHub's compare view) so From→To reads naturally.
			for (const release of [...(app.releases || [])].reverse()) {
				if (!release.hash) {
					continue;
				}
				const message = (release.message || '').split('\n')[0].slice(0, 60);
				const label = release.tag
					? `${release.tag} (${release.hash.slice(0, 7)})`
					: `${release.hash.slice(0, 7)}${message ? ` - ${message}` : ''}`;
				options.push({ label, value: release.hash });
			}

			// Ensure the last patched commit is selectable even if it isn't a
			// tracked release, so the From default can point at it.
			if (
				this.lastPatchHead &&
				!options.some((option) => option.value === this.lastPatchHead)
			) {
				options.push({
					label: `Last patch (${this.lastPatchHead.slice(0, 7)})`,
					value: this.lastPatchHead,
				});
			}

			return options;
		},
		comparePageUrl() {
			const app = this.selectedAppInfo;
			if (!app?.repository_url || !this.fromHash || !this.toHash) {
				return '';
			}
			return `${app.repository_url}/compare/${this.fromHash}...${this.toHash}`;
		},
		comparePatchUrl() {
			return this.comparePageUrl ? `${this.comparePageUrl}.patch` : '';
		},
	},
	methods: {
		clearApp() {
			this.$emit('clear-app-to-patch');
		},
		openCompare(asPatch) {
			const url = asPatch ? this.comparePatchUrl : this.comparePageUrl;
			if (url) {
				window.open(url, '_blank');
			}
		},
		async fetchLastPatchHead() {
			const app = this.selectedApp;
			if (!app) {
				return;
			}
			try {
				const head = await call('press.api.bench.last_patch_head', {
					name: this.group,
					app,
				});
				// Ignore if the user switched apps while the request was in flight
				if (head && this.selectedApp === app) {
					this.lastPatchHead = head;
					this.fromHash = head;
				}
			} catch (e) {
				// Non-critical: fall back to the current-commit default
			}
		},
		validate() {
			if (!this.benchList.length) {
				this.error =
					'This group has no benches, patch cannot be applied.';
				return false;
			}

			if (this.patch && !this.patchFileName) {
				this.error = 'Please enter a patch file Name.';
				return false;
			}

			if (!this.patch && !this.patchURL) {
				this.error = 'Please enter the patch URL or select a patch file.';
				return false;
			}

			if (
				!this.applyToAllBenches &&
				!this.applyToBench &&
				!this.applyToLatestDeploy
			) {
				this.error =
					'Please select a bench or check Apply patch to all active benches';
				return false;
			}

			if (!this.app && !this.applyToApp) {
				this.error = 'Please select an app to patch.';
				return false;
			}

			if (this.patchURL && !this.patchURL.split('?')[0].endsWith('.patch')) {
				this.error =
					'Patch URL does not have a `.patch` extension. Please enter a valid URL,';
				return false;
			}

			return true;
		},
		async fetchApps() {
			try {
				const info = await call('press.api.bench.deploy_information', {
					name: this.group,
				});
				this.deployApps = info?.apps || [];
				if (!this.applyToApp && this.deployApps.length === 1) {
					this.applyToApp = this.deployApps[0].app;
				}
				if (!this.fromHash && this.selectedAppInfo?.current_hash) {
					this.fromHash = this.selectedAppInfo.current_hash;
				}
			} catch (e) {
				this.error = 'Could not load the app list. Please try again.';
			}
		},
		async fetchBenches() {
			try {
				const benches = await call('press.api.client.get_list', {
					doctype: 'Bench',
					fields: ['name'],
					filters: { group: this.group, status: 'Active' },
					limit_page_length: 0,
				});
				this.benchList = (benches || []).map((row) => ({
					value: row.name,
					label: row.name,
				}));
				if (this.benchList.length) {
					this.applyToBench = this.benchList.at(-1).value;
				} else {
					this.error = 'This group has no benches, patch cannot be applied.';
				}
			} catch (e) {
				this.error = 'Could not load benches. Please try again.';
			}
		},
		async applyPatch() {
			if (!this.validate()) {
				return;
			}

			if (!this.patchFileName && this.patchURL) {
				const patchURL = this.patchURL.split('?')[0];
				this.patchFileName = patchURL.split('/').at(-1);
			}

			if (!this.patchFileName.endsWith('.patch')) {
				this.patchFileName += '.patch';
			}

			const app = this.app || this.applyToApp;
			this.applying = true;
			try {
				await call('press.api.bench.apply_patch', {
					release_group: this.group,
					app,
					patch_config: {
						patch: this.patch,
						filename: this.patchFileName,
						patch_url: this.patchURL,
						build_assets: this.buildAssets,
						patch_bench: this.applyToBench,
						patch_all_benches: this.applyToAllBenches,
						patch_latest_deploy: this.applyToLatestDeploy,
					},
				});
				this.close();
				this.$router.push({
					name: 'Release Group Detail Jobs',
					params: { name: this.group },
				});
			} catch (error) {
				this.error = error?.messages?.length
					? error.messages.join('\n')
					: error.message || 'Could not apply the patch.';
			} finally {
				this.applying = false;
			}
		},
		async onPatchFileSelect(e) {
			this.error = '';
			const file = e.target.files?.[0];
			if (!file) {
				return;
			}

			this.patch = await file.text();
			this.patchFileName = file.name;
		},
		clear() {
			this.error = '';
			this.patch = '';
			this.patchFileName = '';
		},
		close() {
			this.show = false;
			this.clear();
		},
	},
};
</script>
