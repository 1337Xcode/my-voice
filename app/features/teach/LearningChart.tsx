/** Words understood by model version as a line chart; `compact` draws the Teach card's sparkline. */
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';
import Svg, { Circle, Line, Polyline, Rect, Text as SvgText } from 'react-native-svg';

import { AppText } from '@/components/AppText';
import { colors, fonts, space } from '@/theme';

export type LearningPoint = { label: string; quiet: number | null; babble: number | null };

type Props = { points: LearningPoint[]; compact?: boolean };

const FULL_HEIGHT = 200;
const COMPACT_HEIGHT = 44;
// Room for the y-axis labels on the left and the version labels underneath.
const AXIS_LEFT = 46;
const AXIS_BOTTOM = 24;

/** "v1 64% quiet, 40% babble; v2 ..." for screen readers. */
function describe(points: LearningPoint[]): string {
  const pct = (value: number | null) => (value === null ? 'not scored' : `${Math.round(value)}%`);
  return points.map((p) => `${p.label}: ${pct(p.quiet)} in quiet, ${pct(p.babble)} in babble`).join('; ');
}

export function LearningChart({ points, compact = false }: Props) {
  const [width, setWidth] = useState(0);
  const height = compact ? COMPACT_HEIGHT : FULL_HEIGHT;
  const left = compact ? 4 : AXIS_LEFT;
  const bottom = compact ? 4 : AXIS_BOTTOM;
  // Points sit inside the axes, so the first and last version labels stay clear of the edges.
  const inset = compact ? 4 : 16;
  const plotWidth = Math.max(0, width - left - 8 - inset * 2);
  const plotHeight = height - bottom - 8;
  const x = (i: number) => left + inset + (points.length === 1 ? plotWidth / 2 : (i / (points.length - 1)) * plotWidth);
  const y = (value: number) => 8 + plotHeight - (value / 100) * plotHeight;
  const series = (key: 'quiet' | 'babble') => points.map((p, i) => (p[key] === null ? null : { x: x(i), y: y(p[key] as number) })).filter((p): p is { x: number; y: number } => p !== null);
  const quiet = series('quiet');
  const babble = compact ? [] : series('babble');
  const line = (pts: { x: number; y: number }[]) => pts.map((p) => `${p.x},${p.y}`).join(' ');

  return (
    <View accessible accessibilityRole="image" accessibilityLabel={`Words understood by version. ${describe(points)}`}>
      <View style={{ height }} onLayout={(e) => setWidth(e.nativeEvent.layout.width)}>
        {width > 0 ? (
          <Svg width={width} height={height}>
            {compact
              ? null
              : [0, 50, 100].map((tick) => (
                  <Line key={tick} x1={left} x2={width - 8} y1={y(tick)} y2={y(tick)} stroke={colors.border} strokeWidth={1} />
                ))}
            {compact
              ? null
              : [0, 50, 100].map((tick) => (
                  <SvgText key={`t${tick}`} x={left - 8} y={y(tick) + 4} fontSize={12} fontFamily={fonts.regular} fill={colors.muted} textAnchor="end">
                    {`${tick}%`}
                  </SvgText>
                ))}
            {compact
              ? null
              : points.map((p, i) => (
                  <SvgText key={p.label} x={x(i)} y={height - 6} fontSize={12} fontFamily={fonts.regular} fill={colors.muted} textAnchor="middle">
                    {p.label}
                  </SvgText>
                ))}
            {babble.length > 1 ? <Polyline points={line(babble)} fill="none" stroke={colors.muted} strokeWidth={2} strokeDasharray="6 5" /> : null}
            {babble.map((p, i) => (
              <Rect key={`b${i}`} x={p.x - 4} y={p.y - 4} width={8} height={8} fill={colors.surface} stroke={colors.muted} strokeWidth={2} />
            ))}
            {quiet.length > 1 ? <Polyline points={line(quiet)} fill="none" stroke={colors.accent} strokeWidth={compact ? 2.5 : 3} /> : null}
            {quiet.map((p, i) => (
              <Circle key={`q${i}`} cx={p.x} cy={p.y} r={compact ? 3 : 5} fill={colors.accent} />
            ))}
          </Svg>
        ) : null}
      </View>
      {compact ? null : (
        <View style={styles.legend} importantForAccessibility="no-hide-descendants">
          <View style={styles.key}>
            <View style={styles.solid} />
            <AppText variant="caption" tone="muted">
              Quiet
            </AppText>
          </View>
          <View style={styles.key}>
            <View style={styles.dashed} />
            <AppText variant="caption" tone="muted">
              Babble 5 dB
            </AppText>
          </View>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  legend: { flexDirection: 'row', gap: space.xl, paddingLeft: AXIS_LEFT, paddingTop: space.sm },
  key: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  solid: { width: 20, height: 3, backgroundColor: colors.accent },
  dashed: { width: 20, height: 0, borderTopWidth: 2, borderStyle: 'dashed', borderColor: colors.muted },
});
