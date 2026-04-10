import Header from "@/components/Header";
import ConferenceTimeline from "@/components/ConferenceTimeline";
import TimelineControls from "@/components/TimelineControls";
import TimelineLegend from "@/components/TimelineLegend";
import conferencesData from "@/utils/conferenceLoader";
import { Conference } from "@/types/conference";
import { TimelineSort, buildConferenceTimelineRows } from "@/utils/conferenceTimeline";
import { addYears } from "date-fns";
import { utcToZonedTime } from "date-fns-tz";
import { useMemo, useState } from "react";

const AOE_TZ = "Etc/GMT+12";

const TimelinePage = () => {
  const [searchQuery, setSearchQuery] = useState("");
  const [sortBy, setSortBy] = useState<TimelineSort>("upcoming-deadline");
  const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set());

  const nowAoe = useMemo(() => utcToZonedTime(new Date(), AOE_TZ), []);
  const rangeStart = useMemo(() => addYears(nowAoe, -1), [nowAoe]);
  const rangeEnd = useMemo(() => addYears(nowAoe, 1), [nowAoe]);

  const tagOptions = useMemo(() => {
    const tags = new Set<string>();
    (conferencesData as Conference[]).forEach((conf) => {
      (conf.tags || []).forEach((tag) => tags.add(tag));
    });
    return Array.from(tags).sort((a, b) => a.localeCompare(b));
  }, []);

  const timelineRows = useMemo(() => {
    return buildConferenceTimelineRows(
      conferencesData as Conference[],
      nowAoe,
      selectedTags,
      searchQuery,
      sortBy,
    );
  }, [nowAoe, selectedTags, searchQuery, sortBy]);

  const handleToggleTag = (tag: string) => {
    setSelectedTags((prev) => {
      const next = new Set(prev);
      if (next.has(tag)) {
        next.delete(tag);
      } else {
        next.add(tag);
      }
      return next;
    });
  };

  return (
    <div className="min-h-screen bg-neutral-light">
      <Header onSearch={setSearchQuery} />
      <div className="mx-auto max-w-7xl space-y-4 px-4 py-4 sm:px-6 lg:px-8">
        <TimelineControls
          sortBy={sortBy}
          onSortChange={setSortBy}
          selectedTags={selectedTags}
          tagOptions={tagOptions}
          onToggleTag={handleToggleTag}
        />
        <TimelineLegend />
        <ConferenceTimeline rows={timelineRows} rangeStart={rangeStart} rangeEnd={rangeEnd} nowAoe={nowAoe} />
      </div>
    </div>
  );
};

export default TimelinePage;
