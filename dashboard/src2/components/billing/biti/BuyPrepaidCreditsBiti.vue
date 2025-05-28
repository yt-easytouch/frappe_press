<template>
	<div>
		
		<ErrorMessage
			class="mt-3"
			:message="$resources.createBitiOrder.error"
		/>
		<div class="mt-4 flex w-full justify-between">
			<div></div>
			<Button
				variant="solid"
				:loading="$resources.createBitiOrder.loading"
				v-if="!isPaymentComplete"
				@click="buyCreditsWithBiti"
			>
				Proceed to payment using Biti
			</Button>
			<Button v-else variant="solid" :loading="isVerifyingPayment"
				>Confirming payment</Button
			>
		</div>
	</div>
</template>
<script>
import { toast } from 'vue-sonner';
import { DashboardError } from '../../../utils/error';

export default {
	name: 'BuyPrepaidCreditsBiti',
	props: {
		amount: {
			default: 0
		},
		minimumAmount: {
			default: 0
		},
		isOnboarding: {
			default: false
		}
	},
	data() {
		return {
			isPaymentComplete: false,
			isVerifyingPayment: false
		};
	},
	mounted() {
		this.BitiCheckoutJS = document.createElement('script');
		this.BitiCheckoutJS.setAttribute(
			'src',
			'https://biti.so/test_checkout/checkout.js?ver=2'
		);
		this.BitiCheckoutJS.async = true;
		document.head.appendChild(this.BitiCheckoutJS);
	},
	resources: {
		createBitiOrder() {
			return {
				url: 'press.api.billing.create_bitipay_order',
				params: {
					amount: this.amount
				},
				onSuccess(data) {
					this.processOrder(data);
				},
				validate() {
					if (this.amount < this.minimumAmount) {
						throw new DashboardError(
							'Amount less than minimum amount required'
						);
					}
				}
			};
		},
		handlePaymentFailed() {
			return {
				url: 'press.api.billing.handle_bitipay_payment_failed',
				onSuccess() {
					console.log('Payment Failed.');
				}
			};
		}
	},
	methods: {
		buyCreditsWithBiti() {
			this.$resources.createBitiOrder.submit();
		},
		processOrder(data) {
			const options = {
				key: data.key_id,
				order_id: data.order_id,
				name: 'Easytouch Cloud',
				image: '/assets/press/images/frappe-cloud-logo.png',
				prefill: {
					email: this.$team.doc.user
				},
				handler: this.handlePaymentSuccess,
				theme: { color: '#171717' }
			};

			const checkout = new BitiCheckout(options);


			// Opens the payment checkout frame
			checkout.open();

			// Attach failure handler
			checkout.on('payment.failed', this.handlePaymentFailed);
			checkout.on('payment.cancel', this.handlePaymentFailed);
			// rzp.on('payment.success', this.handlePaymentSuccess);
		},
		handlePaymentFailed(response) {
			this.$resources.handlePaymentFailed.submit({ response });
			toast.error('Payment failed');
		},
		handlePaymentSuccess() {
			this.isPaymentComplete = true;
			if (this.isOnboarding) {
				this.checkForOnboardingPaymentCompletion();
			} else {
				this.$emit('success');
				toast.success('Payment successful');
			}
		},
		async checkForOnboardingPaymentCompletion() {
			this.isVerifyingPayment = true;
			await this.$team.reload();
			if (!this.$team.doc.payment_mode) {
				setTimeout(this.checkForOnboardingPaymentCompletion, 2000);
			} else {
				this.isVerifyingPayment = false;
				this.$emit('success');
			}
		}
	},
	beforeUnmount() {
		this.BitiCheckoutJS?.remove();
	}
};
</script>
