import { useEffect, useState } from "react";

/**
 * Recharts はSVG属性に CSS変数を使えないため、
 * 現在のテーマのトークン実値をJSで読み取って渡す。
 * Artifact ビューアのトグルは <html data-theme> を書き換えるので監視する。
 */

export interface ChartTokens {
  ink: string;
  ink2: string;
  muted: string;
  grid: string;
  axis: string;
  surface: string;
  accent: string;
  series: Record<string, string>;
}

const readVar = (name: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim();

function readTokens(): ChartTokens {
  return {
    ink: readVar("--ink"),
    ink2: readVar("--ink-2"),
    muted: readVar("--muted"),
    grid: readVar("--grid"),
    axis: readVar("--axis"),
    surface: readVar("--surface"),
    accent: readVar("--accent"),
    series: {
      lifestyle: readVar("--s-lifestyle"),
      menu: readVar("--s-menu"),
      bridal: readVar("--s-bridal"),
      reward: readVar("--s-reward"),
      other: readVar("--s-other"),
    },
  };
}

export function useChartTokens(): ChartTokens {
  const [tokens, setTokens] = useState<ChartTokens>(() => readTokens());
  useEffect(() => {
    const observer = new MutationObserver(() => setTokens(readTokens()));
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme", "class", "style"],
    });
    return () => observer.disconnect();
  }, []);
  return tokens;
}
