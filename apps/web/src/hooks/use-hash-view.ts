import { useEffect, useState } from "react";

import type { AppView } from "../types/research";

const DEFAULT_VIEW: AppView = "operations";
const allowedViews = new Set<AppView>(["operations", "market", "research"]);

function readViewFromHash(hash: string): AppView {
  const normalized = hash.replace(/^#/, "").trim();
  if (allowedViews.has(normalized as AppView)) {
    return normalized as AppView;
  }
  return DEFAULT_VIEW;
}

export function useHashView() {
  const [view, setView] = useState<AppView>(() => readViewFromHash(window.location.hash));

  useEffect(() => {
    if (!window.location.hash) {
      window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#${DEFAULT_VIEW}`);
    }

    const syncFromHash = () => {
      setView(readViewFromHash(window.location.hash));
    };

    syncFromHash();
    window.addEventListener("hashchange", syncFromHash);

    return () => {
      window.removeEventListener("hashchange", syncFromHash);
    };
  }, []);

  function navigate(nextView: AppView) {
    if (nextView === view) {
      return;
    }
    window.location.hash = nextView;
  }

  return {
    view,
    navigate,
  };
}

