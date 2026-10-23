import { useContext } from "react";
import { ConfigContext } from "./ConfigProvider";
import type { ConfigContextValue } from "../types/config";
import { fallbackContextValue } from "./defaults";

export const useAppConfig = (): ConfigContextValue => {
  const context = useContext(ConfigContext);
  if (!context) {
    // Provide safe fallback context for un-wrapped renders (e.g. standalone test cases)
    return fallbackContextValue;
  }
  return context;
};
