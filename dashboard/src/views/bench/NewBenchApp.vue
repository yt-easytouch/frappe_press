<template>
	<WizardCard>
		<div class="mb-6 text-center">
			<h1 class="text-2xl font-bold">Add a New App</h1>
			<p class="text-base text-gray-700">Add an app to your bench</p>
		</div>

		<SelectAppFromGithub @onSelect="d => (app = d)" />

		<ErrorMessage :message="$resources.addApp.error" />

		<Button
			v-if="app"
			:loading="$resources.addApp.loading"
			@click="$resources.addApp.submit()"
			>Add to bench</Button
		>
	</WizardCard>
</template>

<script>
import WizardCard from '@/components/WizardCard.vue';
import SelectAppFromGithub from '@/components/SelectAppFromGithub.vue';

export default {
	name: 'NewBenchApp',
	components: {
		WizardCard,
		SelectAppFromGithub
	},
	props: ['benchName'],
	data() {
		return {
			app: null
		};
	},
	resources: {
		addApp() {
			return {
				url: 'press.api.app.new',
				params: {
					app: {
						name: this.app?.name,
						title: this.app?.title,
						repository_url: this.app?.repository_url,
						branch: this.app?.branch,
						github_installation_id: this.app?.github_installation_id,
						group: this.benchName
					}
				},
				onSuccess() {
					this.$router.push(`/groups/${this.benchName}`);
				}
			};
		}
	}
};
</script>
