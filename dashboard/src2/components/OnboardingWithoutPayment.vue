<template>
	<div class="mx-auto max-w-2xl rounded-lg border-0 px-2 sm:border sm:p-8">
		<div class="prose prose-sm max-w-none">
			<h1 class="text-2xl font-semibold">Welcome to Easytouch Cloud</h1>
			<p>
				Easytouch Cloud makes it easy to manage sites and apps like Easytouch ERP in an
				easy to use dashboard with powerful features like automatic backups,
				custom domains, SSL certificates, custom apps, automatic updates and
				more.
			</p>
		</div>
		<div class="mt-6 space-y-6">
			<div class="flex items-center space-x-2">
				<div class="text-base font-medium">
					Choose an app below to create your first site.
				</div>
			</div>
			<!-- App Chooser -->
			<OnboardingAppSelector :apps="$resources.availableApps.data" />
		</div>
	</div>
</template>
<script>
import OnboardingAppSelector from './OnboardingAppSelector.vue';

export default {
	name: 'Onboarding',
	components: {
		OnboardingAppSelector
	},
	mounted() {
		if (window.posthog?.__loaded) {
			window.posthog.identify(this.$team.doc.user, {
				app: 'frappe_cloud',
				action: 'onboarding'
			});
			window.posthog.startSessionRecording();
		}
	},
	resources: {
		availableApps() {
			return {
				url: 'press.api.marketplace.get_marketplace_apps_for_onboarding',
				auto: true
			};
		}
	}
};
</script>
