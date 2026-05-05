import { getRequestConfig } from "next-intl/server";
import { defaultLocale } from "./config";

export default getRequestConfig(async () => ({
  locale: defaultLocale,
  messages: (await import(`../messages/${defaultLocale}.json`)).default,
}));
