<template>
	<div class="relative h-full">
		<div class="relative z-10 mx-auto py-8 sm:w-max sm:py-32">
			<div class="flex flex-col items-center" @dblclick="redirectForFrappeioAuth">
				<slot name="logo">
					<div class="mx-auto flex items-center space-x-2">
						<ETLogo class="inline-block h-7 w-7" />
						<span
							class="select-none text-xl font-semibold tracking-tight text-gray-900"
						>
							Easytouch Cloud
						</span>
					</div>
				</slot>
			</div>
			<div
				class="mx-auto w-full bg-white px-4 py-8 sm:mt-6 sm:w-96 sm:rounded-lg sm:px-8 sm:shadow-xl"
			>
				<div class="mb-6 text-center" v-if="title">
					<span
						class="text-center text-lg font-medium leading-5 tracking-tight text-gray-900"
					>
						{{ title }}
					</span>
				</div>
				<slot></slot>
			</div>
		</div>
		<div class="absolute bottom-4 z-[1] flex w-full justify-center">
			<YooltechLogo class="h-8" />
		</div>
	</div>
</template>

<script>
import ETLogo from '@/components/icons/ETLogo.vue';
import YooltechLogo from '@/components/icons/YooltechLogo.vue';
import { notify } from '@/utils/toast';

export default {
	name: 'LoginBox',
	props: ['title', 'logo'],
	components: {
		ETLogo,
		YooltechLogo
	},
	mounted() {
		const params = new URLSearchParams(window.location.search);

		if (params.get('showRemoteLoginError')) {
			notify({
				title: 'Token Invalid or Expired',
				color: 'red',
				icon: 'x'
			});
		}
	},
	methods: {
		redirectForFrappeioAuth() {
			window.location = '/f-login';
		}
	}
};
</script>
