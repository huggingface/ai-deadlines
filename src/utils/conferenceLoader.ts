import { Conference } from '@/types/conference';
import { hasUpcomingDeadlines } from './deadlineUtils';

const conferenceModules = import.meta.glob('@/data/conferences/*.yml', { eager: true });

const allConferencesData: Conference[] = [];

for (const path in conferenceModules) {
  const module = conferenceModules[path] as { default: Conference[] };
  if (module.default && Array.isArray(module.default)) {
    allConferencesData.push(...module.default);
  }
}

for (const conf of allConferencesData) {
  if (hasUpcomingDeadlines(conf) && (!Array.isArray(conf.tags) || conf.tags.length === 0)) {
    console.error(
      `Conference "${conf.title}" (${conf.year}) has an upcoming deadline but no tags. ` +
      `Add at least one tag to its YAML file so it appears in filtered views.`
    );
  }
}

export default allConferencesData;
