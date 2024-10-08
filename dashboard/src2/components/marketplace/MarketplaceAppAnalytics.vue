<template>
	<div v-if="$resources.analytics.data">
		<div class="col-span-2 mb-5 rounded-md border">
			<div class="grid grid-cols-2 lg:grid-cols-5">
				<div class="border-b border-r p-5 lg:border-b-0">
					<div class="text-base text-gray-700">Total Installs</div>
					<div class="mt-2 flex items-start justify-between">
						<div>
							<div class="leading-4">
								<span class="text-base text-gray-900">
									{{ installAnalytics.total_installs }}
								</span>
							</div>
						</div>
					</div>
				</div>

				<div class="border-b border-r p-5 lg:border-b-0">
					<div class="text-base text-gray-700">Active Sites</div>
					<div class="mt-2 flex items-start justify-between">
						<div>
							<div class="leading-4">
								<span class="text-base text-gray-900">
									{{ installAnalytics.installs_active_sites }}
								</span>
							</div>
						</div>
					</div>
				</div>

				<div class="border-b border-r p-5 lg:border-b-0">
					<div class="text-base text-gray-700">Active Bench Groups</div>
					<div class="mt-2 flex items-start justify-between">
						<div>
							<div class="leading-4">
								<span class="text-base text-gray-900">
									{{ installAnalytics.installs_active_benches }}
								</span>
							</div>
						</div>
					</div>
				</div>

				<div class="border-b border-r p-5 lg:border-b-0">
					<div class="text-base text-gray-700">Weekly Installs</div>
					<div class="mt-2 flex items-start justify-between">
						<div>
							<div class="leading-4">
								<span class="text-base text-gray-900">
									{{ installAnalytics.installs_last_week }}
								</span>
							</div>
						</div>
					</div>
				</div>

				<div class="border-b border-r p-5 lg:border-b-0">
					<div class="text-base text-gray-700">Total Earnings</div>
					<div class="mt-2 flex items-start justify-between">
						<div>
							<div class="leading-4">
								<span class="text-base text-gray-900">
									{{ $format.userCurrency(totalEarnings) }}
								</span>
							</div>
						</div>
					</div>
				</div>
			</div>
		</div>

		<div
			v-if="$resources.plausible_analytics.data"
			class="grid grid-cols-1 gap-5 lg:grid-cols-2"
		>
			<LineChart
				title="Pageviews"
				type="time"
				key="Page Views"
				:data="
					mapChartAnalytics(
						this.$resources.plausible_analytics.data?.pageviews || []
					)
				"
				unit="views"
				:chartTheme="[$theme.colors.purple[500]]"
				:loading="$resources.plausible_analytics.loading"
				:error="$resources.plausible_analytics.error"
			/>
			<LineChart
				title="Unique Visitors"
				type="time"
				key="Unique Visitors"
				:data="
					mapChartAnalytics(
						this.$resources.plausible_analytics.data?.visitors || []
					)
				"
				unit="visitors"
				:chartTheme="[$theme.colors.green[500]]"
				:loading="$resources.plausible_analytics.loading"
				:error="$resources.plausible_analytics.error"
			/>
		</div>
		<LineChart
			v-if="$resources.plausible_analytics.data"
			class="mt-5"
			title="Weekly Installs"
			type="time"
			key="Weekly Installs"
			:data="
				mapChartAnalytics(
					this.$resources.plausible_analytics.data?.weekly_installs || []
				)
			"
			unit="installs"
			:chartTheme="[$theme.colors.yellow[500]]"
			:loading="$resources.plausible_analytics.loading"
			:error="$resources.plausible_analytics.error"
		/>
	</div>
</template>

<script>
import { DateTime } from 'luxon';
import LineChart from '@/components/charts/LineChart.vue';

export default {
	name: 'MarketplaceAppAnalytics',
	props: {
		app: String
	},
	components: {
		LineChart
	},
	methods: {
		formatDate(data) {
			return data.map(d => d.date);
		},
		getChartOptions(yFormatter) {
			return {
				axisOptions: {
					xIsSeries: true,
					shortenYAxisNumbers: 1
				},
				lineOptions: {
					hideDots: true,
					regionFill: true
				},
				tooltipOptions: {
					formatTooltipX: d => {
						return DateTime.fromISO(d).toLocaleString(DateTime.DATE_MED);
					},
					formatTooltipY: yFormatter
				}
			};
		},
		mapChartAnalytics(data) {
			if (!data) return;
			return {
				datasets: [data.map(d => [+new Date(d.date), d.value])]
			};
		}
	},
	resources: {
		analytics() {
			return {
				url: 'press.api.marketplace.analytics',
				auto: true,
				params: {
					name: this.app
				}
			};
		},
		plausible_analytics() {
			return {
				url: 'press.api.analytics.plausible_analytics',
				auto: true,
				params: {
					name: this.app
				}
			};
		}
	},
	computed: {
		installAnalytics() {
			if (
				!this.$resources.analytics.loading &&
				this.$resources.analytics.data
			) {
				return this.$resources.analytics.data;
			}
			return {};
		},
		totalEarnings() {
			if (!this.installAnalytics.total_payout.inr_amount) return 0;

			if (this.$team.doc.currency === 'INR') {
				return (
					this.installAnalytics.total_payout.inr_amount +
					this.installAnalytics.total_payout.usd_amount * 82
				);
			} else {
				return (
					this.installAnalytics.total_payout.inr_amount / 82 +
					this.installAnalytics.total_payout.usd_amount
				);
			}
		}
	}
};
</script>
