export const PLATO_CLERK_AUTH_PROVIDER = "clerk";

export function isClerkAuthEnabled(): boolean {
  return process.env.NEXT_PUBLIC_PLATO_AUTH_PROVIDER === PLATO_CLERK_AUTH_PROVIDER;
}

export function isHostedBillingEnabled(): boolean {
  return (
    isClerkAuthEnabled() &&
    process.env.NEXT_PUBLIC_PLATO_HOSTED_BILLING === "enabled"
  );
}
