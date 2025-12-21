export interface Deadline {
  type: string;
  label: string;
  date: string;
  timezone?: string;
}

export interface Conference {
  id: string;
  title: string;
  full_name?: string;
  year: number;
  link?: string;
  deadline: string; // Keep for backward compatibility
  deadlines?: Deadline[]; // New multiple deadlines support
  timezone?: string;
  date: string;
  place?: string;
  city?: string;
  country?: string;
  venue?: string;
  tags?: string[];
  note?: string;
  abstract_deadline?: string; // Keep for backward compatibility
  start?: string;
  end?: string;
  rankings?: string;
  hindex?: number;
  rebuttal_period_start?: string;
  rebuttal_period_end?: string;
  final_decision_date?: string;
  review_release_date?: string;
  submission_deadline?: string;
  timezone_submission?: string;
  commitment_deadline?: string;
  paperslink?: string;
  pwclink?: string;
  era_rating?: string; // ERA rating (e.g., 'a', 'b', 'c')
} 