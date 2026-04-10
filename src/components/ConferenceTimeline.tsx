import { addMonths, format, isAfter, startOfMonth } from "date-fns";
import { TimelineSeriesRow } from "@/utils/conferenceTimeline";
import ConferenceTimelineRow from "@/components/ConferenceTimelineRow";

interface ConferenceTimelineProps {
  rows: TimelineSeriesRow[];
  rangeStart: Date;
  rangeEnd: Date;
  nowAoe: Date;
}

const toPercent = (date: Date, rangeStart: Date, rangeEnd: Date) => {
  const total = rangeEnd.getTime() - rangeStart.getTime();
  if (total <= 0) return 0;
  const value = ((date.getTime() - rangeStart.getTime()) / total) * 100;
  return Math.min(100, Math.max(0, value));
};

const ConferenceTimeline = ({ rows, rangeStart, rangeEnd, nowAoe }: ConferenceTimelineProps) => {
  const monthTicks: Date[] = [];
  let cursor = startOfMonth(rangeStart);
  while (!isAfter(cursor, rangeEnd)) {
    monthTicks.push(cursor);
    cursor = addMonths(cursor, 1);
  }

  const yearTicks = monthTicks.filter((tick) => tick.getMonth() === 0);
  const nowPercent = toPercent(nowAoe, rangeStart, rangeEnd);

  return (
    <div className="rounded-lg bg-white p-4 shadow">
      <div className="overflow-x-auto" style={{ WebkitOverflowScrolling: "touch" }}>
        <div className="grid min-w-[1600px] grid-cols-[220px_1fr]">
          <div className="sticky left-0 z-20 border-b bg-white py-2 pr-3 text-xs text-neutral-500">Conference</div>
          <div className="relative border-b py-2 text-xs text-neutral-500">
            <div
              className="pointer-events-none absolute bottom-0 top-0 w-[2px] -translate-x-1/2 bg-emerald-600/80"
              style={{ left: `${nowPercent}%` }}
              title={`Now (AoE): ${format(nowAoe, "yyyy-MM-dd HH:mm")}`}
            />

            <div className="relative h-4">
              {yearTicks.map((tick) => (
                <span
                  key={`year-${tick.toISOString()}`}
                  className="absolute -translate-x-1/2 text-[11px] font-medium text-neutral-700"
                  style={{ left: `${toPercent(tick, rangeStart, rangeEnd)}%` }}
                >
                  {format(tick, "yyyy")}
                </span>
              ))}
            </div>
            <div className="relative mt-1 h-4">
              {monthTicks.map((tick) => (
                <span
                  key={`month-${tick.toISOString()}`}
                  className="absolute -translate-x-1/2 text-[11px]"
                  style={{ left: `${toPercent(tick, rangeStart, rangeEnd)}%` }}
                >
                  {format(tick, "MMM")}
                </span>
              ))}
            </div>
          </div>

          {rows.map((row) => (
            <ConferenceTimelineRow
              key={row.seriesKey}
              row={row}
              rangeStart={rangeStart}
              rangeEnd={rangeEnd}
              nowPercent={nowPercent}
              referenceYear={nowAoe.getFullYear()}
            />
          ))}

          {rows.length === 0 && (
            <>
              <div className="sticky left-0 z-10 bg-white py-8 pr-3" />
              <div className="py-8 text-center text-sm text-neutral-500">No conferences match current filters.</div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default ConferenceTimeline;
