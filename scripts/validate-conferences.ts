import { z } from "zod";
import * as fs from "fs";
import * as path from "path";
import { fileURLToPath } from "url";
import * as yaml from "js-yaml";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CONFERENCES_DIR = path.resolve(__dirname, "../src/data/conferences");

const DATETIME_RE = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/;
const UTC_OFFSET_RE = /^(UTC|GMT)([+-]\d{1,2})?$/;

const KNOWN_ABBREVIATIONS = new Set([
  "PST",
  "PDT",
  "MST",
  "MDT",
  "CST",
  "CDT",
  "EST",
  "EDT",
  "CET",
  "CEST",
  "BST",
  "IST",
  "JST",
  "KST",
  "AEST",
  "AEDT",
]);

function isValidTimezone(tz: string): boolean {
  if (tz === "AoE") return true;
  if (UTC_OFFSET_RE.test(tz)) return true;
  if (KNOWN_ABBREVIATIONS.has(tz)) return true;
  try {
    Intl.DateTimeFormat(undefined, { timeZone: tz });
    return true;
  } catch {
    return false;
  }
}

const timezoneSchema = z.string().refine(isValidTimezone, {
  message:
    "Must be 'AoE', a valid IANA timezone, UTC/GMT offset, or known abbreviation (e.g. PST)",
});

const deadlineEntrySchema = z.object({
  type: z.string().min(1, "Deadline type is required"),
  label: z.string().min(1, "Deadline label is required"),
  date: z.string().regex(DATETIME_RE, {
    message: "Deadline date must match 'YYYY-MM-DD HH:mm:ss'",
  }),
  timezone: timezoneSchema.optional(),
});

// Helper: accept both undefined and null for optional fields (YAML parses missing vs explicit null)
function nullable<T extends z.ZodTypeAny>(schema: T) {
  return schema.nullable().optional();
}

const conferenceSchema = z.object({
  title: z.string().min(1, "Title is required"),
  year: z.number().int().positive("Year must be a positive integer"),
  id: z
    .string()
    .min(1, "ID is required")
    .regex(
      /^[a-z0-9+-]+$/,
      "ID must be lowercase alphanumeric (hyphens and plus signs allowed)"
    ),
  full_name: nullable(z.string()),
  link: nullable(z.string().url("Link must be a valid URL")),
  deadline: nullable(
    z.string().regex(DATETIME_RE, {
      message: "deadline must match 'YYYY-MM-DD HH:mm:ss'",
    })
  ),
  deadlines: nullable(z.array(deadlineEntrySchema)),
  timezone: nullable(timezoneSchema),
  date: z.string().min(1, "Date is required"),
  place: nullable(z.string()),
  city: nullable(z.string()),
  country: nullable(z.string()),
  venue: nullable(z.string()),
  tags: nullable(z.array(z.string())),
  note: nullable(z.string()),
  abstract_deadline: nullable(
    z.string().regex(DATETIME_RE, {
      message: "abstract_deadline must match 'YYYY-MM-DD HH:mm:ss'",
    })
  ),
  start: nullable(z.union([z.string(), z.date()])),
  end: nullable(z.union([z.string(), z.date()])),
  rankings: nullable(z.string()),
  hindex: nullable(z.number()),
  rebuttal_period_start: nullable(z.string()),
  rebuttal_period_end: nullable(z.string()),
  final_decision_date: nullable(z.string()),
  review_release_date: nullable(z.string()),
  submission_deadline: nullable(z.string()),
  timezone_submission: nullable(z.string()),
  commitment_deadline: nullable(z.string()),
  paperslink: nullable(z.string()),
  pwclink: nullable(z.string()),
  era_rating: nullable(z.string()),
});

interface ValidationIssue {
  file: string;
  index: number;
  id?: string;
  severity: "error" | "warning";
  message: string;
}

function extractYearFromId(id: string): number | null {
  const match = id.match(/(\d{2,4})(?:[a-z]*)$/);
  if (!match) return null;
  const digits = match[1];
  if (digits.length === 4) return parseInt(digits, 10);
  if (digits.length === 2) return 2000 + parseInt(digits, 10);
  return null;
}

function validateConferences(): boolean {
  const issues: ValidationIssue[] = [];
  const allIds = new Map<string, string>(); // id -> file path

  const files = fs
    .readdirSync(CONFERENCES_DIR)
    .filter((f) => f.endsWith(".yml") || f.endsWith(".yaml"))
    .sort();

  if (files.length === 0) {
    console.error("No conference YAML files found in", CONFERENCES_DIR);
    process.exit(1);
  }

  for (const file of files) {
    const filePath = path.join(CONFERENCES_DIR, file);
    const relPath = path.relative(process.cwd(), filePath);

    let content: unknown;
    try {
      const raw = fs.readFileSync(filePath, "utf-8");
      content = yaml.load(raw);
    } catch (e) {
      issues.push({
        file: relPath,
        index: -1,
        severity: "error",
        message: `Failed to parse YAML: ${e instanceof Error ? e.message : String(e)}`,
      });
      continue;
    }

    if (!Array.isArray(content)) {
      issues.push({
        file: relPath,
        index: -1,
        severity: "error",
        message: "File must contain a YAML array of conference entries",
      });
      continue;
    }

    for (let i = 0; i < content.length; i++) {
      const entry = content[i];
      const entryId = entry?.id ?? `entry[${i}]`;
      const result = conferenceSchema.safeParse(entry);

      if (!result.success) {
        for (const issue of result.error.issues) {
          issues.push({
            file: relPath,
            index: i,
            id: entryId,
            severity: "error",
            message: `${issue.path.join(".")}: ${issue.message}`,
          });
        }
        continue;
      }

      const conf = result.data;

      // Warn if conference has no deadline information at all
      const hasDeadline = conf.deadline || (conf.deadlines && conf.deadlines.length > 0);
      if (!hasDeadline) {
        issues.push({
          file: relPath,
          index: i,
          id: conf.id,
          severity: "warning",
          message: "No 'deadline' or 'deadlines' - conference won't appear in deadline views",
        });
      }

      // Check for duplicate IDs across all files
      const existingFile = allIds.get(conf.id);
      if (existingFile) {
        issues.push({
          file: relPath,
          index: i,
          id: conf.id,
          severity: "error",
          message: `Duplicate id '${conf.id}' (also in ${existingFile})`,
        });
      } else {
        allIds.set(conf.id, relPath);
      }

      // Warn if id year suffix doesn't match year field
      const idYear = extractYearFromId(conf.id);
      if (idYear !== null && idYear !== conf.year) {
        issues.push({
          file: relPath,
          index: i,
          id: conf.id,
          severity: "warning",
          message: `ID year suffix (${idYear}) does not match year field (${conf.year})`,
        });
      }

      // Warn about missing tags on entries that have future deadlines
      if (!conf.tags || conf.tags.length === 0) {
        issues.push({
          file: relPath,
          index: i,
          id: conf.id,
          severity: "warning",
          message: "Missing 'tags' - conference will not appear in filtered views",
        });
      }

      // Warn about missing era_rating
      if (!conf.era_rating) {
        issues.push({
          file: relPath,
          index: i,
          id: conf.id,
          severity: "warning",
          message: "Missing 'era_rating' - conference has no ERA rating defined",
        });
      }

      // Warn about timezone abbreviations (not portable)
      const allTimezones: string[] = [];
      if (conf.timezone) allTimezones.push(conf.timezone);
      if (conf.deadlines) {
        for (const d of conf.deadlines) {
          if (d.timezone) allTimezones.push(d.timezone);
        }
      }
      for (const tz of allTimezones) {
        if (KNOWN_ABBREVIATIONS.has(tz)) {
          issues.push({
            file: relPath,
            index: i,
            id: conf.id,
            severity: "warning",
            message: `Timezone '${tz}' is an abbreviation - prefer 'AoE', IANA name, or UTC/GMT offset`,
          });
          break;
        }
      }
    }
  }

  // Print results
  const errors = issues.filter((i) => i.severity === "error");
  const warnings = issues.filter((i) => i.severity === "warning");

  if (warnings.length > 0) {
    console.log(`\n⚠ ${warnings.length} warning(s):\n`);
    for (const w of warnings) {
      const loc = w.index >= 0 ? ` [${w.id ?? `#${w.index}`}]` : "";
      console.log(`  ${w.file}${loc}: ${w.message}`);
    }
  }

  if (errors.length > 0) {
    console.log(`\n✗ ${errors.length} error(s):\n`);
    for (const e of errors) {
      const loc = e.index >= 0 ? ` [${e.id ?? `#${e.index}`}]` : "";
      console.log(`  ${e.file}${loc}: ${e.message}`);
    }
    console.log(
      `\nValidation failed: ${errors.length} error(s), ${warnings.length} warning(s) across ${files.length} files.\n`
    );
    return false;
  }

  console.log(
    `\n✓ All ${allIds.size} conferences in ${files.length} files passed validation.` +
      (warnings.length > 0 ? ` (${warnings.length} warning(s))` : "") +
      "\n"
  );
  return true;
}

const success = validateConferences();
process.exit(success ? 0 : 1);
