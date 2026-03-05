# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview
This is an AI Conference Deadlines web application that displays submission deadlines for top AI conferences like NeurIPS and ICLR. It's a React/TypeScript web app built with Vite, using shadcn-ui components and Tailwind CSS.

## Development Commands
```bash
# Install dependencies
npm i

# Start development server (runs on http://localhost:8080)
npm run dev

# Build for production
npm run build

# Build for development
npm run build:dev

# Lint code
npm run lint

# Preview production build
npm preview
```

## Architecture

### Core Structure
- **Frontend**: React 18 + TypeScript + Vite
- **UI Framework**: shadcn-ui components with Radix UI primitives
- **Styling**: Tailwind CSS with custom animations
- **Data Source**: Individual YAML files per conference (`src/data/conferences/`) updated via GitHub Actions
- **State Management**: React hooks, no external state management library

### Key Directories
- `src/components/` - React components (UI components in `ui/` subdirectory)
- `src/pages/` - Route components (Index, Calendar, NotFound)
- `src/data/` - Conference data in YAML format
- `src/types/` - TypeScript type definitions
- `src/utils/` - Utility functions for date handling and conference processing
- `src/hooks/` - Custom React hooks

### Main Components
- `ConferenceList` - Primary list view of conferences
- `ConferenceCard` - Individual conference display card
- `ConferenceDialog` - Detailed conference information modal
- `FilterBar` - Conference filtering and search functionality
- `ConferenceCalendar` - Calendar view of conferences
- `Header` - Navigation and app header

### Data Model
Conferences are defined by the `Conference` interface in `src/types/conference.ts` with properties including:
- Basic info: `title`, `year`, `id`, `full_name`, `link`
- Dates: `deadline`, `abstract_deadline`, `date`, `start`, `end`
- Location: `city`, `country`, `venue`
- Metadata: `tags`, `hindex`, `note`

### Configuration Files
- `vite.config.ts` - Vite configuration with YAML plugin for loading conference data
- `tailwind.config.ts` - Tailwind CSS configuration with custom theme
- `components.json` - shadcn-ui component configuration
- `tsconfig.json` - TypeScript configuration

### Data Updates
Conference data is automatically updated via GitHub Actions workflow (`.github/workflows/update-conferences.yml`) that fetches from ccfddl repository and creates pull requests with updates to individual conference files.

### Path Aliases
- `@/*` maps to `src/*` for cleaner imports

## Data Conventions
- **Timezone for deadlines**: Always use `AoE` (Anywhere on Earth, equivalent to UTC-12) for conference deadline timezones. Never use `UTC-12` — use `AoE` for consistency and clarity.
- Supported timezone formats in YAML: `AoE`, IANA names (e.g. `Asia/Seoul`), `UTC±X`, `GMT±X`

## Development Notes
- The app uses a YAML plugin to import conference data directly in components
- All UI components follow shadcn-ui patterns and conventions
- The project uses React Router for client-side routing
- Date handling uses `date-fns` and `date-fns-tz` for timezone support