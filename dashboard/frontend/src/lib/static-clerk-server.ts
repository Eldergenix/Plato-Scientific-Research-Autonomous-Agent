import { NextResponse } from "next/server";
import type { NextFetchEvent, NextRequest } from "next/server";

type StaticSession = {
  userId: null;
  orgId: null;
  redirectToSignIn: () => NextResponse;
};

const staticSession: StaticSession = {
  userId: null,
  orgId: null,
  redirectToSignIn: () => NextResponse.redirect(new URL("/login", "http://localhost")),
};

export async function auth(): Promise<StaticSession> {
  return staticSession;
}

export async function clerkClient() {
  return {
    billing: {
      getOrganizationBillingSubscription: async () => null,
      getUserBillingSubscription: async () => null,
    },
    organizations: {
      getOrganization: async () => null,
      getOrganizationMembershipList: async () => null,
    },
  };
}

export function clerkMiddleware() {
  return (_request: NextRequest, _event: NextFetchEvent) => NextResponse.next();
}
