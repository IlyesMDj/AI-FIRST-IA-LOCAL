import type { Metadata } from "next";
import { cookies, headers } from "next/headers";
import "./globals.css";
import { Shell } from "@/components/shell";
import { I18nProvider, type Lang } from "@/lib/i18n";

export const metadata: Metadata = {
  title: "Recruiter Copilot Local",
  description: "Local, private AI assistant for recruiters",
  robots: { index: false, follow: false },
};

// Dark "HUD" theme is the default identity; the light variant is opt-in.
// "rcl-theme" (new key): earlier light/dark choices made before the HUD redesign are ignored.
const themeScript = `(function(){var d=true;try{d=localStorage.getItem('rcl-theme')!=='light'}catch(e){}document.documentElement.classList.toggle('dark',d)})();`;

async function detectLang(): Promise<Lang> {
  const c = (await cookies()).get("lang")?.value;
  if (c === "fr" || c === "en") return c;
  const al = ((await headers()).get("accept-language") || "").toLowerCase();
  return al.startsWith("fr") ? "fr" : "en";
}

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const lang = await detectLang();
  return (
    <html lang={lang} className="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>
        <I18nProvider initialLang={lang}>
          <Shell>{children}</Shell>
        </I18nProvider>
      </body>
    </html>
  );
}
