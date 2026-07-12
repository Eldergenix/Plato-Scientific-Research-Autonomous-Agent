"use client";

import type { ReactNode } from "react";

type ChildrenProps = {
  children?: ReactNode;
};

type ShowProps = ChildrenProps & {
  when?: "signed-in" | "signed-out";
};

export function ClerkProvider({ children }: ChildrenProps) {
  return <>{children}</>;
}

export function Show({ children, when }: ShowProps) {
  return when === "signed-in" ? null : <>{children}</>;
}

export function SignInButton({ children }: ChildrenProps) {
  return <>{children}</>;
}

export function SignUpButton({ children }: ChildrenProps) {
  return <>{children}</>;
}

export function useAuth() {
  return {
    isLoaded: true,
    isSignedIn: false,
    userId: null,
    orgId: null,
  };
}

export function UserButton() {
  return null;
}

export function OrganizationSwitcher() {
  return null;
}

export function PricingTable() {
  return null;
}

export function CreateOrganization() {
  return null;
}

export function UserProfile() {
  return null;
}

export function OrganizationProfile() {
  return null;
}

export function SignIn() {
  return null;
}

export function SignUp() {
  return null;
}
