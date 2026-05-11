"use client";

import * as React from "react";

type AuthModeContextValue = {
  clerkAuthEnabled: boolean;
};

const AuthModeContext = React.createContext<AuthModeContextValue>({
  clerkAuthEnabled: false,
});

export function AuthModeProvider({
  children,
  clerkAuthEnabled,
}: {
  children: React.ReactNode;
  clerkAuthEnabled: boolean;
}) {
  return (
    <AuthModeContext.Provider value={{ clerkAuthEnabled }}>
      {children}
    </AuthModeContext.Provider>
  );
}

export function useAuthMode(): AuthModeContextValue {
  return React.useContext(AuthModeContext);
}
