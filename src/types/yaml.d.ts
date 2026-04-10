import type { Conference } from '@/types/conference';

declare module '*.yml' {
  const data: Conference[];
  export default data;
}
