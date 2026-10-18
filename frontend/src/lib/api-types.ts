import type { components } from "./api-schema";

type Schema = components["schemas"];

export type SymbolsResponse = Schema["SymbolsResponse"];
export type PricesResponse = Schema["PricesResponse"];
export type StoredBar = Schema["StoredBar"];
export type FFTConfig = Schema["FFTConfig"];
export type HarmonicConfig = Schema["HarmonicConfig"];
export type ForecastRequest = Schema["ForecastRequest"];
export type BacktestRequest = Schema["BacktestRequest"];
export type CycleResult = Schema["CycleResult"];
export type ForecastResult = Schema["ForecastResult"];
export type BacktestResult = Schema["BacktestResult"];
export type ForecastPoint = Schema["ForecastPoint"];
export type TurningPoint = Schema["TurningPoint"];
export type Metrics = Schema["Metrics"];
export type AnalysisResponse = Schema["AnalysisResponse"];
export type DataProvenance = Schema["DataProvenance"];
export type SectorResponse = Schema["SectorResponse"];
export type SectorResult = Schema["SectorResult"];
export type SectorPoint = Schema["SectorPoint"];

type AnalysisOf<Kind extends AnalysisResponse["kind"], Result> = Omit<
  AnalysisResponse,
  "kind" | "result"
> & { kind: Kind; result: Result };

export type CycleAnalysis = AnalysisOf<"cycles", CycleResult>;
export type ForecastAnalysis = AnalysisOf<"forecast", ForecastResult>;
export type BacktestAnalysis = AnalysisOf<"backtest", BacktestResult>;
export type TypedAnalysis = CycleAnalysis | ForecastAnalysis | BacktestAnalysis;

/** A complete read, rather than one API pagination envelope. */
export type PriceHistory = Omit<PricesResponse, "limit" | "offset" | "has_more"> & {
  page_count: number;
};
