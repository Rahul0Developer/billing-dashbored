// ---- Lightweight i18n: English + Hindi (Indian retail context) ----
import React, { createContext, useContext, useState, useCallback } from "react";

export type Lang = "en" | "hi";

const dict: Record<string, Record<Lang, string>> = {
  "nav.pos": { en: "POS Billing Counter", hi: "POS बिलिंग काउंटर" },
  "nav.sales": { en: "Sales & Invoices", hi: "बिक्री और चालान" },
  "nav.shifts": { en: "Register Shifts & Z-Report", hi: "शिफ्ट और Z-रिपोर्ट" },
  "nav.dashboard": { en: "Store BI & P&L", hi: "स्टोर BI और लाभ-हानि" },
  "nav.branches": { en: "Multi-Branch Stores", hi: "मल्टी-ब्रांच स्टोर" },
  "nav.inventory": { en: "Inventory & Stock", hi: "इन्वेंटरी और स्टॉक" },
  "nav.customers": { en: "Customer Footfall", hi: "ग्राहक फुटफॉल" },
  "nav.expenses": { en: "Expenses Tracker", hi: "खर्च ट्रैकर" },
  "nav.reports": { en: "Data Exports", hi: "डेटा निर्यात" },
  "nav.users": { en: "Staff & Audit Trail", hi: "स्टाफ़ और ऑडिट" },
  "pos.search": { en: "Scan barcode or search product…", hi: "बारकोड स्कैन करें या खोजें…" },
  "pos.cart": { en: "Current Sale", hi: "वर्तमान बिक्री" },
  "pos.emptyCart": { en: "No items yet — scan a barcode or search to start billing.", hi: "अभी कोई वस्तु नहीं — बिलिंग शुरू करने के लिए स्कैन करें।" },
  "pos.subtotal": { en: "Subtotal", hi: "उप-योग" },
  "pos.savings": { en: "Customer Savings", hi: "ग्राहक बचत" },
  "pos.discount": { en: "Discounts", hi: "छूट" },
  "pos.tax": { en: "GST (CGST + SGST)", hi: "जीएसटी (CGST + SGST)" },
  "pos.total": { en: "Grand Total", hi: "कुल राशि" },
  "pos.checkout": { en: "Complete Sale", hi: "बिक्री पूर्ण करें" },
  "pos.change": { en: "Change to Return", hi: "वापसी शेष" },
  "pos.tender": { en: "Amount Tendered", hi: "प्रदान की गई राशि" },
  "pos.customer": { en: "Customer", hi: "ग्राहक" },
  "pos.walkin": { en: "Walk-in Customer", hi: "वॉक-इन ग्राहक" },
  "pos.points": { en: "Loyalty Points", hi: "लॉयल्टी अंक" },
  "pos.redeem": { en: "Redeem", hi: "रिडीम" },
  "pay.cash": { en: "Cash", hi: "नकद" },
  "pay.upi": { en: "UPI", hi: "यूपीआई" },
  "pay.card": { en: "Card", hi: "कार्ड" },
  "pay.wallet": { en: "Wallet", hi: "वॉलेट" },
  "common.cancel": { en: "Cancel", hi: "रद्द करें" },
  "common.confirm": { en: "Confirm", hi: "पुष्टि करें" },
  "common.close": { en: "Close", hi: "बंद करें" },
  "common.save": { en: "Save", hi: "सहेजें" },
  "common.delete": { en: "Delete", hi: "हटाएँ" },
  "common.loading": { en: "Loading…", hi: "लोड हो रहा है…" },
  "common.retry": { en: "Retry", hi: "पुनः प्रयास" },
  "common.export": { en: "Export", hi: "निर्यात" },
  "common.print": { en: "Print", hi: "प्रिंट" },
  "common.managerPin": { en: "Manager PIN", hi: "मैनेजर पिन" },
  "login.title": { en: "Sign in to Apex POS", hi: "Apex POS में साइन इन करें" },
  "login.username": { en: "Username", hi: "यूज़रनेम" },
  "login.pin": { en: "Password / PIN", hi: "पासवर्ड / पिन" },
  "login.signIn": { en: "Sign In", hi: "साइन इन" },
  "status.online": { en: "Online", hi: "ऑनलाइन" },
  "status.offline": { en: "Offline — sales will queue & sync", hi: "ऑफ़लाइन — बिक्री क्यू में सिंक होगी" },
};

interface I18nCtx {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: string) => string;
}

const Ctx = createContext<I18nCtx>({
  lang: "en",
  setLang: () => undefined,
  t: (k) => k,
});

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>((localStorage.getItem("apex_lang") as Lang) || "en");
  const setLang = useCallback((l: Lang) => {
    localStorage.setItem("apex_lang", l);
    document.documentElement.lang = l;
    setLangState(l);
  }, []);
  const t = useCallback(
    (key: string) => dict[key]?.[lang] ?? dict[key]?.en ?? key,
    [lang],
  );
  return <Ctx.Provider value={{ lang, setLang, t }}>{children}</Ctx.Provider>;
}

export const useI18n = () => useContext(Ctx);
