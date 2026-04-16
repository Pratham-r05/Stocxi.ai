interface SentimentChartProps {
  data: { date: string; reddit_score: number; twitter_score: number }[];
}

// Format a date string like "2024-04-10" → "Apr 10"
function fmtDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  } catch {
    return dateStr;
  }
}

// Map a score in [-1, 1] to a SVG Y coordinate within the chart area
function scoreToY(score: number, chartTop: number, chartHeight: number): number {
  // score=+1 → top (chartTop), score=-1 → bottom (chartTop + chartHeight)
  return chartTop + ((1 - score) / 2) * chartHeight;
}

const VIEWBOX_WIDTH = 600;
const VIEWBOX_HEIGHT = 160;
const PADDING_LEFT = 12;
const PADDING_RIGHT = 12;
const PADDING_TOP = 12;
const PADDING_BOTTOM = 36; // room for x-axis labels
const CHART_TOP = PADDING_TOP;
const CHART_HEIGHT = VIEWBOX_HEIGHT - PADDING_TOP - PADDING_BOTTOM;
const CHART_LEFT = PADDING_LEFT;
const CHART_WIDTH = VIEWBOX_WIDTH - PADDING_LEFT - PADDING_RIGHT;

export default function SentimentChart({ data }: SentimentChartProps) {
  if (!data || data.length < 2) {
    return (
      <div className="w-full flex items-center justify-center h-40 text-zinc-500 text-sm">
        No chart data
      </div>
    );
  }

  const n = data.length;

  // X positions evenly distributed
  const xOf = (i: number) =>
    n === 1
      ? CHART_LEFT + CHART_WIDTH / 2
      : CHART_LEFT + (i / (n - 1)) * CHART_WIDTH;

  const redditPoints = data
    .map((d, i) => `${xOf(i)},${scoreToY(d.reddit_score, CHART_TOP, CHART_HEIGHT)}`)
    .join(" ");

  const twitterPoints = data
    .map((d, i) => `${xOf(i)},${scoreToY(d.twitter_score, CHART_TOP, CHART_HEIGHT)}`)
    .join(" ");

  const zeroY = scoreToY(0, CHART_TOP, CHART_HEIGHT);
  const halfPosY = scoreToY(0.5, CHART_TOP, CHART_HEIGHT);
  const halfNegY = scoreToY(-0.5, CHART_TOP, CHART_HEIGHT);

  return (
    <div className="w-full">
      <svg
        viewBox={`0 0 ${VIEWBOX_WIDTH} ${VIEWBOX_HEIGHT}`}
        width="100%"
        height="160"
        aria-label="Sentiment chart"
      >
        {/* Gridline at +0.5 */}
        <line
          x1={CHART_LEFT}
          y1={halfPosY}
          x2={CHART_LEFT + CHART_WIDTH}
          y2={halfPosY}
          stroke="#27272a"
          strokeWidth="1"
        />

        {/* Gridline at -0.5 */}
        <line
          x1={CHART_LEFT}
          y1={halfNegY}
          x2={CHART_LEFT + CHART_WIDTH}
          y2={halfNegY}
          stroke="#27272a"
          strokeWidth="1"
        />

        {/* Zero gridline */}
        <line
          x1={CHART_LEFT}
          y1={zeroY}
          x2={CHART_LEFT + CHART_WIDTH}
          y2={zeroY}
          stroke="#3f3f46"
          strokeWidth="1"
          strokeDasharray="4 4"
        />

        {/* Reddit line */}
        <polyline
          points={redditPoints}
          fill="none"
          stroke="#a78bfa"
          strokeWidth="2"
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {/* Twitter line */}
        <polyline
          points={twitterPoints}
          fill="none"
          stroke="#22d3ee"
          strokeWidth="2"
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {/* Reddit dots */}
        {data.map((d, i) => (
          <g key={`r-${i}`}>
            <title>{`Reddit ${fmtDate(d.date)}: ${d.reddit_score.toFixed(2)}`}</title>
            <circle
              cx={xOf(i)}
              cy={scoreToY(d.reddit_score, CHART_TOP, CHART_HEIGHT)}
              r="3"
              fill="#a78bfa"
            />
          </g>
        ))}

        {/* Twitter dots */}
        {data.map((d, i) => (
          <g key={`t-${i}`}>
            <title>{`Twitter/X ${fmtDate(d.date)}: ${d.twitter_score.toFixed(2)}`}</title>
            <circle
              cx={xOf(i)}
              cy={scoreToY(d.twitter_score, CHART_TOP, CHART_HEIGHT)}
              r="3"
              fill="#22d3ee"
            />
          </g>
        ))}

        {/* X axis date labels */}
        {data.map((d, i) => (
          <text
            key={`label-${i}`}
            x={xOf(i)}
            y={VIEWBOX_HEIGHT - 6}
            textAnchor="middle"
            fontSize="9"
            fill="#71717a"
          >
            {fmtDate(d.date)}
          </text>
        ))}
      </svg>

      {/* Legend */}
      <div className="flex items-center gap-5 mt-2 justify-center">
        <div className="flex items-center gap-1.5">
          <span className="inline-block w-2.5 h-2.5 rounded-full bg-violet-400" />
          <span className="text-xs text-zinc-400">Reddit</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="inline-block w-2.5 h-2.5 rounded-full bg-cyan-400" />
          <span className="text-xs text-zinc-400">Twitter/X</span>
        </div>
      </div>
    </div>
  );
}
