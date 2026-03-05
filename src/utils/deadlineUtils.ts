import { Conference, Deadline } from "@/types/conference";
import { getDeadlineInLocalTime } from './dateUtils';
import { isValid, isPast } from "date-fns";

/**
 * Get all deadlines for a conference, including both new format and legacy format
 */
export function getAllDeadlines(conference: Conference): Deadline[] {
  const deadlines: Deadline[] = [];
  const seenTypes = new Set<string>();
  
  // Add new format deadlines first (they take priority)
  if (conference.deadlines && conference.deadlines.length > 0) {
    conference.deadlines.forEach(deadline => {
      deadlines.push(deadline);
      seenTypes.add(deadline.type);
    });
  }
  
  // Add legacy format deadlines for backward compatibility, but only if not already present
  if (conference.abstract_deadline && !seenTypes.has('abstract')) {
    deadlines.push({
      type: 'abstract',
      label: 'Abstract Submission',
      date: conference.abstract_deadline,
      timezone: conference.timezone
    });
  }
  
  if (conference.deadline && !seenTypes.has('submission')) {
    deadlines.push({
      type: 'submission',
      label: 'Paper Submission',
      date: conference.deadline,
      timezone: conference.timezone
    });
  }
  
  if (conference.commitment_deadline && !seenTypes.has('commitment')) {
    deadlines.push({
      type: 'commitment',
      label: 'Commitment',
      date: conference.commitment_deadline,
      timezone: conference.timezone
    });
  }
  
  if (conference.review_release_date && !seenTypes.has('review_release')) {
    deadlines.push({
      type: 'review_release',
      label: 'Reviews Released',
      date: conference.review_release_date,
      timezone: conference.timezone
    });
  }
  
  if (conference.rebuttal_period_start && !seenTypes.has('rebuttal_start')) {
    deadlines.push({
      type: 'rebuttal_start',
      label: 'Rebuttal Period Start',
      date: conference.rebuttal_period_start,
      timezone: conference.timezone
    });
  }
  
  if (conference.rebuttal_period_end && !seenTypes.has('rebuttal_end')) {
    deadlines.push({
      type: 'rebuttal_end',
      label: 'Rebuttal Period End',
      date: conference.rebuttal_period_end,
      timezone: conference.timezone
    });
  }
  
  if (conference.final_decision_date && !seenTypes.has('final_decision')) {
    deadlines.push({
      type: 'final_decision',
      label: 'Final Decision',
      date: conference.final_decision_date,
      timezone: conference.timezone
    });
  }
  
  // Sort deadlines by date
  deadlines.sort((a, b) => {
    const aDate = getDeadlineInLocalTime(a.date, a.timezone || conference.timezone);
    const bDate = getDeadlineInLocalTime(b.date, b.timezone || conference.timezone);
    
    if (!aDate || !bDate) return 0;
    return aDate.getTime() - bDate.getTime();
  });
  
  return deadlines;
}

/**
 * Get the next upcoming deadline for a conference
 */
export function getNextUpcomingDeadline(conference: Conference): Deadline | null {
  const allDeadlines = getAllDeadlines(conference);
  
  if (allDeadlines.length === 0) {
    return null;
  }
  
  // Filter out past deadlines and invalid dates
  const upcomingDeadlines = allDeadlines.filter(deadline => {
    const deadlineDate = getDeadlineInLocalTime(deadline.date, deadline.timezone || conference.timezone);
    return deadlineDate && isValid(deadlineDate) && !isPast(deadlineDate);
  });
  
  if (upcomingDeadlines.length === 0) {
    return null;
  }
  
  // Sort by date and return the earliest
  upcomingDeadlines.sort((a, b) => {
    const aDate = getDeadlineInLocalTime(a.date, a.timezone || conference.timezone);
    const bDate = getDeadlineInLocalTime(b.date, b.timezone || conference.timezone);
    
    if (!aDate || !bDate) return 0;
    return aDate.getTime() - bDate.getTime();
  });
  
  return upcomingDeadlines[0];
}

/**
 * Get the primary deadline for sorting purposes (next upcoming or most recent past)
 */
export function getPrimaryDeadline(conference: Conference): Deadline | null {
  const nextDeadline = getNextUpcomingDeadline(conference);
  
  if (nextDeadline) {
    return nextDeadline;
  }
  
  // If no upcoming deadlines, return the most recent past deadline
  const allDeadlines = getAllDeadlines(conference);
  
  if (allDeadlines.length === 0) {
    return null;
  }
  
  // Filter valid dates and sort by date (most recent first)
  const validDeadlines = allDeadlines.filter(deadline => {
    const deadlineDate = getDeadlineInLocalTime(deadline.date, deadline.timezone || conference.timezone);
    return deadlineDate && isValid(deadlineDate);
  });
  
  if (validDeadlines.length === 0) {
    return null;
  }
  
  validDeadlines.sort((a, b) => {
    const aDate = getDeadlineInLocalTime(a.date, a.timezone || conference.timezone);
    const bDate = getDeadlineInLocalTime(b.date, b.timezone || conference.timezone);
    
    if (!aDate || !bDate) return 0;
    return bDate.getTime() - aDate.getTime(); // Most recent first
  });
  
  return validDeadlines[0];
}

/**
 * Check if a conference has any upcoming deadlines
 */
export function hasUpcomingDeadlines(conference: Conference): boolean {
  return getNextUpcomingDeadline(conference) !== null;
}

/**
 * Get all upcoming deadlines sorted by date
 */
export function getUpcomingDeadlines(conference: Conference): Deadline[] {
  const allDeadlines = getAllDeadlines(conference);
  
  // Filter out past deadlines and invalid dates
  const upcomingDeadlines = allDeadlines.filter(deadline => {
    const deadlineDate = getDeadlineInLocalTime(deadline.date, deadline.timezone || conference.timezone);
    return deadlineDate && isValid(deadlineDate) && !isPast(deadlineDate);
  });
  
  // Sort by date
  upcomingDeadlines.sort((a, b) => {
    const aDate = getDeadlineInLocalTime(a.date, a.timezone || conference.timezone);
    const bDate = getDeadlineInLocalTime(b.date, b.timezone || conference.timezone);
    
    if (!aDate || !bDate) return 0;
    return aDate.getTime() - bDate.getTime();
  });
  
  return upcomingDeadlines;
}

/**
 * Get the number of days remaining until a deadline
 * Returns null if the deadline date is invalid
 */
export function getDaysRemaining(deadline: Deadline, fallbackTimezone?: string): number | null {
  const deadlineDate = getDeadlineInLocalTime(deadline.date, deadline.timezone || fallbackTimezone);
  if (!deadlineDate || !isValid(deadlineDate)) return null;
  
  const now = new Date();
  const diff = deadlineDate.getTime() - now.getTime();
  return Math.ceil(diff / (1000 * 60 * 60 * 24));
}

/**
 * Get the color class for a countdown based on days remaining
 */
export function getCountdownColorClass(daysRemaining: number | null): string {
  if (daysRemaining === null) return "text-neutral-600";
  if (daysRemaining <= 0) return "text-neutral-600";
  if (daysRemaining <= 7) return "text-red-600";
  if (daysRemaining <= 30) return "text-orange-600";
  return "text-green-600";
}
