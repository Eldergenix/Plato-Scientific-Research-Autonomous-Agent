"use client";

import * as React from "react";

type AuthModeContextValue = {
  clerkAuthEnabled: boolean;
  clerkAuthMisconfigured: boolean;
  clerkAuthError: string | null;
};

const AuthModeContext = React.createContext<AuthModeContextValue>({
  clerkAuthEnabled: false,
  clerkAuthMisconfigured: false,
  clerkAuthError: null,
});

export function AuthModeProvider({
  children,
  clerkAuthEnabled,
  clerkAuthMisconfigured,
  clerkAuthError,
}: {
  children: React.ReactNode;
  clerkAuthEnabled: boolean;
  clerkAuthMisconfigured: boolean;
  clerkAuthError: string | null;
}) {
  return (
    <AuthModeContext.Provider
      value={{ clerkAuthEnabled, clerkAuthMisconfigured, clerkAuthError }}
    >
      {children}
    </AuthModeContext.Provider>
  );
}

export function useAuthMode(): AuthModeContextValue {
  return React.useContext(AuthModeContext);
}
