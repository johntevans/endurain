/**
 * Chart provider seam. Activity and Home surfaces render metric charts through
 * this abstraction so the concrete charting library (Chart.js, unovis, ECharts,
 * …) can be swapped — or omitted on minimal builds — without touching any view.
 * Self-hosted instances run the default no-op until a provider is registered
 * during bootstrap.
 *
 * This module intentionally ships no charting dependency; it defines only the
 * contract and registration seam.
 */
import { createProviderSeam } from '@/composables/createProviderSeam'

/** Supported chart geometries. */
export type ChartKind = 'line' | 'area' | 'bar'

/** A single named data series. */
export interface ChartSeries {
  /** Series label shown in legends/tooltips. */
  label: string
  /** Numeric values aligned to {@link ChartRenderOptions.labels}. */
  data: number[]
  /** Optional explicit colour; providers may fall back to a palette. */
  color?: string
  /**
   * Renders the series as a dashed reference line — e.g. a target/goal — drawn
   * as a line overlay even on bar charts (a mixed bar/line chart). Providers
   * without dashed support fall back to a solid line.
   */
  dashed?: boolean
  /** homelab fork: `false` leaves the series out of the legend (e.g. an average line). */
  legend?: boolean
  /** homelab fork: `false` draws a line without the tinted fill below it. */
  fill?: boolean
  /**
   * homelab fork: colours each line segment by the value it ends at (e.g. a
   * zone colour); the series `color` still marks it in legends and tooltips.
   */
  segmentColor?: (value: number) => string
}

/** homelab fork: a horizontal band of the y-axis tinted behind the data (a zone). */
export interface ChartYBand {
  /** Lower edge, in raw values. */
  from: number
  /** Upper edge, in raw values. */
  to: number
  /** 6-digit hex colour; drawn as a light tint. */
  color: string
}

/** Options controlling a single chart render. */
export interface ChartRenderOptions {
  /** Chart geometry. */
  kind: ChartKind
  /** One or more series to plot. */
  series: ChartSeries[]
  /** X-axis category labels aligned to each series' values. */
  labels?: string[]
  /**
   * Optional unit suffix for x-axis values (e.g. `km`, `mi`). Appended to the
   * tooltip's x value so a hover reads `0.7 km` rather than a bare `0.7`; axis
   * ticks stay unitless to avoid clutter. Empty/omitted for self-describing
   * axes such as time.
   */
  xUnit?: string
  /**
   * Optional formatter applied to y-axis ticks and tooltip values. Lets a
   * fitness surface render domain units (pace `M:SS`, `bpm`, `W`) without the
   * view knowing the charting library. Receives the raw numeric value.
   */
  valueFormat?: (value: number) => string
  /**
   * Inverts the y-axis so smaller values sit at the top. Used for pace charts
   * where a lower (faster) pace is "better".
   */
  invertY?: boolean
  /**
   * homelab fork: fixed y-axis bounds and tick step, in raw values. Samples
   * outside are clipped at the edge instead of stretching the axis.
   */
  yRange?: { min: number; max: number; step?: number }
  /** homelab fork: caps the x-axis labels and keeps them horizontal. */
  xMaxTicks?: number
  /**
   * homelab fork: hovering anywhere over an x position shows every series'
   * value there, instead of only when the pointer is on a line.
   */
  hoverIndex?: boolean
  /** homelab fork: tinted y-axis bands drawn behind the series (zones). */
  yBands?: ChartYBand[]
  /** homelab fork: exactly these y-axis ticks (e.g. zone edges) instead of automatic ones. */
  yTicks?: number[]
  /**
   * Enables interactive pan/zoom along the x-axis (wheel + drag on desktop,
   * pinch on touch). Providers without zoom support ignore this.
   */
  zoom?: boolean
}

/** Imperative handle to a mounted chart, returned by {@link ChartProvider.mount}. */
export interface ChartInstance {
  /** Re-renders the chart with new options (e.g. after data refresh). */
  update(options: ChartRenderOptions): void
  /** Tears down the chart and releases resources. */
  destroy(): void
}

/**
 * Pluggable chart renderer.
 *
 * @property name - Stable identifier of the concrete implementation.
 * @property mount - Mounts a chart into `target` and returns its handle.
 */
export interface ChartProvider {
  readonly name: string
  mount(target: HTMLElement, options: ChartRenderOptions): ChartInstance
}

/**
 * Default provider used until a real one is registered. It renders nothing and
 * reports as unavailable so consumers can show a fallback surface instead.
 */
const noopChartProvider: ChartProvider = {
  name: 'noop',
  mount() {
    return {
      update() {},
      destroy() {},
    }
  },
}

const seam = createProviderSeam<ChartProvider>(noopChartProvider)

/**
 * Registers the active chart provider. Call once during bootstrap on
 * deployments that bundle a charting library.
 *
 * @param next - The provider to install.
 */
export function setChartProvider(next: ChartProvider): void {
  seam.set(next)
}

/** Result of {@link useChartProvider}. */
export interface UseChartProvider {
  /** The active provider (the no-op when none is registered). */
  provider: ChartProvider
  /** `true` when a real provider has been registered. */
  isAvailable: boolean
}

/**
 * Chart provider hook.
 *
 * @returns The active provider plus an availability flag for fallback UI.
 */
export function useChartProvider(): UseChartProvider {
  return {
    provider: seam.get(),
    isAvailable: seam.isRegistered(),
  }
}
