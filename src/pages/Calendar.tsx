import { useState } from "react";
import conferencesData from "@/utils/conferenceLoader";
import { Conference } from "@/types/conference";
import { Calendar as CalendarIcon, Tag, X, Plus } from "lucide-react"; // Added X and Plus imports
import { Calendar } from "@/components/ui/calendar";
import { parseISO, format, isValid, isSameMonth, isSameYear, isSameDay, isSameWeek } from "date-fns";
import { Toggle } from "@/components/ui/toggle";
import Header from "@/components/Header";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

const categoryColors: Record<string, string> = {
  "machine-learning": "bg-purple-500",
  "computer-vision": "bg-orange-500",
  "natural-language-processing": "bg-blue-500",
  "robotics": "bg-green-500",
  "signal-processing": "bg-cyan-500",
  "speech": "bg-teal-500",
  "data-mining": "bg-pink-500",
  "reinforcement-learning": "bg-yellow-500",
  "automated-planning": "bg-amber-500",
  "other": "bg-gray-500"
};

const categoryNames: Record<string, string> = {
  "machine-learning": "Machine Learning",
  "computer-vision": "Computer Vision",
  "natural-language-processing": "NLP",
  "robotics": "Robotics",
  "signal-processing": "Signal Processing",
  "speech": "Speech",
  "data-mining": "Data Mining",
  "reinforcement-learning": "Reinforcement Learning",
  "automated-planning": "Automated Planning",
  "other": "Other"
};

// Add this array to maintain the exact order we want
const orderedCategories = [
  "machine-learning",
  "computer-vision",
  "natural-language-processing",
  "robotics",
  "reinforcement-learning",
  "signal-processing",
  "speech",
  "data-mining",
  "automated-planning",
  "other"
] as const;

const mapLegacyTag = (tag: string): string => {
  const legacyTagMapping: Record<string, string> = {
    "web-search": "other",
    "human-computer-interaction": "other",
    "computer-graphics": "other",
    // reinforcement-learning is already a proper tag, so no mapping needed
    // Add any other legacy mappings here
  };
  return legacyTagMapping[tag] || tag;
};

const CalendarPage = () => {
  const [selectedDate, setSelectedDate] = useState<Date | undefined>(new Date());
  const [isYearView, setIsYearView] = useState(true);
  const [currentMonth, setCurrentMonth] = useState<Date>(new Date());
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedDayEvents, setSelectedDayEvents] = useState<{ date: Date | null, events: { deadlines: Conference[], conferences: Conference[] } }>({
    date: null,
    events: { deadlines: [], conferences: [] }
  });
  const [selectedCategories, setSelectedCategories] = useState<Set<string>>(
    new Set(orderedCategories)
  );
  const [showDeadlines, setShowDeadlines] = useState(true);
  const [currentYear, setCurrentYear] = useState(new Date().getFullYear());
  
  const safeParseISO = (dateString: string | undefined | number): Date | null => {
    if (!dateString) return null;
    if (dateString === 'TBD') return null;
    
    const isDate = (value: unknown): value is Date => {
      return value && Object.prototype.toString.call(value) === '[object Date]';
    };

    if (isDate(dateString)) return dateString;
    
    try {
      if (typeof dateString === 'object') {
        return null;
      }
      
      const dateStr = typeof dateString === 'number' ? dateString.toString() : dateString;
      
      let normalizedDate = dateStr;
      const parts = dateStr.split('-');
      if (parts.length === 3) {
        normalizedDate = `${parts[0]}-${parts[1].padStart(2, '0')}-${parts[2].padStart(2, '0')}`;
      }
      
      const parsedDate = parseISO(normalizedDate);
      return isValid(parsedDate) ? parsedDate : null;
    } catch (error) {
      console.error("Error parsing date:", dateString);
      return null;
    }
  };

  const getEvents = (date: Date) => {
    return conferencesData.filter((conf: Conference) => {
      // Map the conference tags to our new category system
      const mappedTags = conf.tags?.map(mapLegacyTag) || [];
      
      const matchesSearch = searchQuery === "" || 
        conf.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (conf.full_name && conf.full_name.toLowerCase().includes(searchQuery.toLowerCase()));

      // Use mapped tags for category matching
      const matchesCategory = mappedTags.some(tag => selectedCategories.has(tag));

      const deadlineDate = safeParseISO(conf.deadline);
      const startDate = safeParseISO(conf.start);
      const endDate = safeParseISO(conf.end);

      // Check if a date is in the current year
      const isInCurrentYear = (date: Date | null) => {
        return date && date.getFullYear() === currentYear;
      };

      // If showing deadlines and no categories selected, only show deadlines
      if (showDeadlines && selectedCategories.size === 0) {
        return deadlineDate && isInCurrentYear(deadlineDate) && matchesSearch;
      }

      if (!matchesSearch || (!matchesCategory && selectedCategories.size > 0)) return false;

      // Check if either deadline or conference dates are in the current year
      const deadlineInYear = showDeadlines && deadlineDate && isInCurrentYear(deadlineDate);
      const conferenceInYear = (startDate && isInCurrentYear(startDate)) || 
                             (endDate && isInCurrentYear(endDate)) ||
                             (startDate && endDate && 
                              startDate.getFullYear() <= currentYear && 
                              endDate.getFullYear() >= currentYear);

      return deadlineInYear || (selectedCategories.size > 0 && conferenceInYear);
    });
  };

  const getDayEvents = (date: Date) => {
    const deadlines = showDeadlines ? conferencesData.filter(conf => {
      const deadlineDate = safeParseISO(conf.deadline);
      const matchesCategory = selectedCategories.size === 0 ? true :
        (Array.isArray(conf.tags) && conf.tags.some(tag => selectedCategories.has(tag)));
      return deadlineDate && 
             isSameDay(deadlineDate, date) && 
             deadlineDate.getFullYear() === currentYear && 
             matchesCategory;
    }) : [];

    const conferences = selectedCategories.size > 0 ? conferencesData.filter(conf => {
      const startDate = safeParseISO(conf.start);
      const endDate = safeParseISO(conf.end);
      const matchesCategory = Array.isArray(conf.tags) && 
        conf.tags.some(tag => selectedCategories.has(tag));

      if (!matchesCategory) return false;

      if (startDate && endDate) {
        return startDate.getFullYear() <= currentYear && 
               endDate.getFullYear() >= currentYear &&
               date >= startDate && date <= endDate;
      } else if (startDate) {
        return startDate.getFullYear() === currentYear && isSameDay(startDate, date);
      }
      return false;
    }) : [];

    return {
      deadlines: deadlines.filter(conf => 
        searchQuery === "" || 
        conf.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (conf.full_name && conf.full_name.toLowerCase().includes(searchQuery.toLowerCase()))
      ),
      conferences: conferences.filter(conf => 
        searchQuery === "" || 
        conf.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (conf.full_name && conf.full_name.toLowerCase().includes(searchQuery.toLowerCase()))
      )
    };
  };

  const renderEventPreview = (events: { deadlines: Conference[], conferences: Conference[] }) => {
    if (events.deadlines.length === 0 && events.conferences.length === 0) return null;
    
    return (
      <div className="p-2 max-w-[200px]">
        {events.deadlines.length > 0 && (
          <div className="mb-2">
            <p className="font-semibold text-red-500">Deadlines:</p>
            {events.deadlines.map(conf => (
              <div key={conf.id} className="text-sm">{conf.title}</div>
            ))}
          </div>
        )}
        {events.conferences.length > 0 && (
          <div>
            <p className="font-semibold text-purple-600">Conferences:</p>
            {events.conferences.map(conf => (
              <div key={conf.id} className="text-sm">{conf.title}</div>
            ))}
          </div>
        )}
      </div>
    );
  };

  const isEndOfWeek = (date: Date) => date.getDay() === 6; // Saturday
  const isStartOfWeek = (date: Date) => date.getDay() === 0; // Sunday

  const getConferenceLineStyle = (date: Date) => {
    // If only showing deadlines and no categories are selected, don't show any conference lines
    if (selectedCategories.size === 0 && showDeadlines) {
      return [];
    }

    return conferencesData
      .filter(conf => {
        const startDate = safeParseISO(conf.start);
        const endDate = safeParseISO(conf.end);
        // Only show conference dates if categories are selected
        const matchesCategory = selectedCategories.size > 0 && 
          (Array.isArray(conf.tags) && conf.tags.some(tag => selectedCategories.has(tag)));
        return startDate && endDate && date >= startDate && date <= endDate && matchesCategory;
      })
      .map(conf => {
        const startDate = safeParseISO(conf.start);
        const endDate = safeParseISO(conf.end);
        
        if (!startDate || !endDate) return null;

        let style = "w-[calc(100%+1rem)] -left-2 relative";
        
        if (isSameDay(date, startDate)) {
          style += " rounded-l-sm";
        }
        if (isSameDay(date, endDate)) {
          style += " rounded-r-sm";
        }
        
        const color = conf.tags && conf.tags[0] ? categoryColors[conf.tags[0]] : "bg-gray-500";

        return { style, color };
      });
  };

  const renderDayContent = (date: Date) => {
    const dayEvents = getDayEvents(date);
    const hasEvents = dayEvents.deadlines.length > 0 || dayEvents.conferences.length > 0;

    const conferenceStyles = getConferenceLineStyle(date);

    const hasDeadline = showDeadlines && dayEvents.deadlines.length > 0;

    const handleDayClick = (e: React.MouseEvent) => {
      e.preventDefault(); // Prevent default calendar behavior
      e.stopPropagation(); // Stop event propagation
      setSelectedDayEvents({
        date,
        events: dayEvents
      });
    };

    return (
      <div 
        className="relative w-full h-full flex flex-col"
        onClick={handleDayClick}
      >
        <div className="h-10 flex items-center justify-center">
          <span>{format(date, 'd')}</span>
        </div>

        <div className="absolute bottom-2 left-0 right-0 flex flex-col-reverse gap-[1px]">
          {conferenceStyles.map((style, index) => (
            <div 
              key={`conf-${index}`} 
              className={`h-[2px] ${style.style} ${style.color}`} 
            />
          ))}
          {hasDeadline && (
            <div className="h-[2px] w-[calc(100%+1rem)] -left-2 relative bg-red-500" />
          )}
        </div>

        {hasEvents && (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger className="absolute inset-0" />
              <TooltipContent>
                {renderEventPreview(dayEvents)}
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}
      </div>
    );
  };

  const renderEventDetails = (conf: Conference) => {
    const deadlineDate = safeParseISO(conf.deadline);
    const startDate = safeParseISO(conf.start);
    const endDate = safeParseISO(conf.end);

    return (
      <div className="border-b last:border-b-0 pb-4 last:pb-0 mb-4 last:mb-0">
        <div className="flex justify-between items-start">
          <div>
            <h3 className="font-semibold text-lg text-neutral-900">{conf.title}</h3>
            {conf.full_name && (
              <p className="text-sm text-neutral-600 mb-2">{conf.full_name}</p>
            )}
          </div>
          {conf.link && (
            <a 
              href={conf.link} 
              target="_blank" 
              rel="noopener noreferrer" 
              className="text-blue-500 hover:text-blue-600 flex items-center gap-1 text-sm"
            >
              Website
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                <polyline points="15 3 21 3 21 9" />
                <line x1="10" y1="14" x2="21" y2="3" />
              </svg>
            </a>
          )}
        </div>
        
        <div className="space-y-2 mt-3">
          {deadlineDate && (
            <div className="flex items-start gap-2">
              <span className="font-medium text-sm text-neutral-900">Deadline:</span>
              <div className="text-sm text-neutral-900">
                <div>{format(deadlineDate, 'MMMM d, yyyy')}</div>
                {conf.timezone && (
                  <div className="text-neutral-500 text-xs">
                    Timezone: {conf.timezone}
                  </div>
                )}
              </div>
            </div>
          )}
          
          {startDate && (
            <div className="flex items-start gap-2">
              <span className="font-medium text-sm text-neutral-900">Date:</span>
              <div className="text-sm text-neutral-900">
                <div>
                  {format(startDate, 'MMMM d')}
                  {endDate ? ` - ${format(endDate, 'MMMM d, yyyy')}` : 
                    `, ${format(startDate, 'yyyy')}`}
                </div>
              </div>
            </div>
          )}

          {conf.place && (
            <div className="flex items-start gap-2">
              <span className="font-medium text-sm text-neutral-900">Location:</span>
              <span className="text-sm text-neutral-900">{conf.place}</span>
            </div>
          )}

          {conf.note && (
            <div className="flex items-start gap-2 mt-2">
              <span className="font-medium text-sm text-neutral-900">Note:</span>
              <div className="text-sm text-neutral-900" 
                dangerouslySetInnerHTML={{ __html: conf.note }} 
              />
            </div>
          )}
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          {Array.isArray(conf.tags) && conf.tags.map((tag) => (
            <span 
              key={tag} 
              className="inline-flex items-center px-2 py-1 rounded-full text-xs bg-neutral-100 text-neutral-900"
            >
              <Tag className="h-3 w-3 mr-1" />
              {categoryNames[tag] || tag}
            </span>
          ))}
        </div>
      </div>
    );
  };

  const categories = orderedCategories
    .filter(category => 
      conferencesData.some(conf => conf.tags?.includes(category))
    )
    .map(category => [category, categoryColors[category]]);

  const renderLegend = () => {
    return (
      <div className="flex flex-wrap gap-3 justify-center items-center mb-4">
        <div className="flex gap-3 items-center">
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  onClick={() => setShowDeadlines(!showDeadlines)}
                  className={`
                    flex items-center gap-2 px-3 py-1.5 
                    rounded-lg border border-red-200 
                    bg-white hover:bg-red-50 
                    transition-all duration-200
                    cursor-pointer
                    ${showDeadlines ? 'ring-2 ring-primary ring-offset-2' : ''}
                  `}
                >
                  <div className="w-3 h-3 bg-red-500 rounded-full" />
                  <span className="text-sm">Submission Deadlines</span>
                </button>
              </TooltipTrigger>
              <TooltipContent>
                <p>Click to toggle submission deadlines</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>

        <div className="h-6 w-px bg-neutral-200" /> {/* Divider */}

        {categories.map(([tag, color]) => (
          <TooltipProvider key={tag}>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  onClick={() => {
                    const newCategories = new Set(selectedCategories);
                    if (newCategories.has(tag)) {
                      newCategories.delete(tag);
                    } else {
                      newCategories.add(tag);
                    }
                    setSelectedCategories(newCategories);
                  }}
                  className={`
                    flex items-center gap-2 px-3 py-1.5 
                    rounded-lg border border-neutral-200 
                    bg-white hover:bg-neutral-50 
                    transition-all duration-200
                    cursor-pointer
                    ${selectedCategories.has(tag) ? 'ring-2 ring-primary ring-offset-2' : ''}
                  `}
                >
                  <div className={`w-3 h-3 rounded-full ${color}`} />
                  <span className="text-sm">{categoryNames[tag] || tag}</span>
                </button>
              </TooltipTrigger>
              <TooltipContent>
                <p>Click to toggle {categoryNames[tag] || tag}</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        ))}

        {selectedCategories.size < Object.keys(categoryColors).length && (
          <button
            onClick={() => {
              setSelectedCategories(new Set(orderedCategories));
              setShowDeadlines(true);
            }}
            className="text-sm text-green-600 bg-green-50 hover:bg-green-100 hover:text-green-700
              px-3 py-1.5 rounded-lg border border-green-200
              transition-colors flex items-center gap-2"
          >
            <Plus className="h-4 w-4" />
            Select All
          </button>
        )}

        {selectedCategories.size > 0 && (
          <button
            onClick={() => {
              setSelectedCategories(new Set());
              setShowDeadlines(false);
            }}
            className="text-sm text-red-600 bg-red-50 hover:bg-red-100 hover:text-red-700
              px-3 py-1.5 rounded-lg border border-red-200
              transition-colors flex items-center gap-2"
          >
            <X className="h-4 w-4" />
            Deselect All
          </button>
        )}
      </div>
    );
  };

  const renderViewToggle = () => {
    return (
      <div className="flex flex-col items-center gap-4 mb-6">
        <div className="bg-neutral-100 rounded-lg p-1 inline-flex">
          <button
            onClick={() => setIsYearView(false)}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              !isYearView 
                ? 'bg-white shadow-sm text-primary' 
                : 'text-neutral-600 hover:text-neutral-900'
            }`}
          >
            Month View
          </button>
          <button
            onClick={() => setIsYearView(true)}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              isYearView 
                ? 'bg-white shadow-sm text-primary' 
                : 'text-neutral-600 hover:text-neutral-900'
            }`}
          >
            Year View
          </button>
        </div>
        
        {isYearView && (
          <div className="flex items-center gap-4">
            <button
              onClick={() => {
                const newYear = currentYear - 1;
                setCurrentYear(newYear);
                setSelectedDate(new Date(newYear, 0, 1)); // Set to January 1st of the new year
              }}
              className="p-2 hover:bg-neutral-100 rounded-full transition-colors"
              aria-label="Previous year"
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path d="M15 18l-6-6 6-6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
            <span className="text-lg font-semibold">{currentYear}</span>
            <button
              onClick={() => {
                const newYear = currentYear + 1;
                setCurrentYear(newYear);
                setSelectedDate(new Date(newYear, 0, 1)); // Set to January 1st of the new year
              }}
              className="p-2 hover:bg-neutral-100 rounded-full transition-colors"
              aria-label="Next year"
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path d="M9 18l6-6-6-6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
          </div>
        )}
      </div>
    );
  };

  const handleMonthChange = (month: Date) => {
    setCurrentMonth(month);
    setSelectedDate(month);
  };

  return (
    <div className="min-h-screen bg-neutral-light">
      <Header onSearch={setSearchQuery} />

      {searchQuery && (
        <div className="p-6 bg-white border-b">
          <div className="max-w-4xl mx-auto">
            <h2 className="text-lg font-semibold mb-4">
              Search Results for "{searchQuery}"
            </h2>
            <div className="space-y-4">
              {getEvents(new Date()).map((conf: Conference) => (
                <div 
                  key={conf.id || conf.title} 
                  className="p-4 border rounded-lg hover:bg-neutral-50 cursor-pointer"
                  onClick={() => {
                    const deadlineDate = safeParseISO(conf.deadline);
                    const startDate = safeParseISO(conf.start);
                    
                    if (deadlineDate) {
                      setSelectedDate(deadlineDate);
                      setSelectedDayEvents({
                        date: deadlineDate,
                        events: getDayEvents(deadlineDate)
                      });
                    } else if (startDate) {
                      setSelectedDate(startDate);
                      setSelectedDayEvents({
                        date: startDate,
                        events: getDayEvents(startDate)
                      });
                    }
                  }}
                >
                  <div className="flex justify-between items-start">
                    <div>
                      <h3 className="font-semibold">{conf.title}</h3>
                      {conf.full_name && (
                        <p className="text-sm text-neutral-600">{conf.full_name}</p>
                      )}
                    </div>
                    {conf.deadline && conf.deadline !== 'TBD' && (
                      <span className="text-sm text-red-500">
                        Deadline: {format(safeParseISO(conf.deadline)!, 'MMM d, yyyy')}
                      </span>
                    )}
                  </div>
                  {Array.isArray(conf.tags) && conf.tags.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {conf.tags.map(tag => (
                        <span 
                          key={tag}
                          className="inline-flex items-center px-2 py-1 rounded-full text-xs bg-neutral-100"
                        >
                          <Tag className="h-3 w-3 mr-1" />
                          {categoryNames[tag] || tag}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              {getEvents(new Date()).length === 0 && (
                <p className="text-neutral-600">No conferences found matching your search.</p>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="p-6">
        <div className="max-w-7xl mx-auto">
          {renderViewToggle()}
          {renderLegend()}

          <div className="grid grid-cols-1 gap-8">
            <div className="mx-auto w-full max-w-4xl">
              <Calendar
                mode="single"
                selected={selectedDate}
                onSelect={setSelectedDate}
                numberOfMonths={isYearView ? 12 : 1}
                showOutsideDays={false}
                defaultMonth={new Date(currentYear, 0)}
                month={isYearView ? new Date(currentYear, 0) : currentMonth}
                onMonthChange={handleMonthChange}
                fromMonth={isYearView ? new Date(currentYear, 0) : undefined}
                toMonth={isYearView ? new Date(currentYear, 11) : undefined}
                className="bg-white rounded-lg p-6 shadow-sm mx-auto w-full"
                components={{
                  Day: ({ date, displayMonth, ...props }) => {
                    const isOutsideDay = date.getMonth() !== displayMonth.getMonth();
                    if (isOutsideDay) {
                      return null;
                    }
                    return (
                      <div 
                        role="button"
                        tabIndex={0}
                        {...props} 
                        className="w-full h-full p-2 cursor-pointer"
                      >
                        {renderDayContent(date)}
                      </div>
                    );
                  },
                }}
                classNames={{
                  months: `grid ${isYearView ? 'grid-cols-3 gap-4' : ''} justify-center`,
                  month: "space-y-4",
                  caption: "flex justify-center pt-1 relative items-center mb-4",
                  caption_label: "text-lg font-semibold",
                  head_row: "flex",
                  head_cell: "text-muted-foreground rounded-md w-10 font-normal text-[0.8rem]",
                  row: "flex w-full mt-2",
                  cell: "h-16 w-10 text-center text-sm p-0 relative focus-within:relative focus-within:z-20 hover:bg-neutral-50",
                  day: "h-16 w-10 p-0 font-normal hover:bg-neutral-100 rounded-lg transition-colors",
                  day_today: "bg-neutral-100 text-primary font-semibold",
                  day_outside: "hidden",
                  nav: "space-x-1 flex items-center",
                  nav_button: isYearView ? "hidden" : "h-7 w-7 bg-transparent p-0 opacity-50 hover:opacity-100",
                  nav_button_previous: "absolute left-1",
                  nav_button_next: "absolute right-1"
                }}
              />
            </div>
          </div>
        </div>
      </div>

      <Dialog 
        open={selectedDayEvents.date !== null}
        onOpenChange={() => setSelectedDayEvents({ date: null, events: { deadlines: [], conferences: [] } })}
      >
        <DialogContent 
          className="max-w-2xl max-h-[80vh] overflow-y-auto"
          aria-describedby="dialog-description"
        >
          <DialogHeader>
            <DialogTitle>
              Events for {selectedDayEvents.date ? format(selectedDayEvents.date, 'MMMM d, yyyy') : ''}
            </DialogTitle>
            <div id="dialog-description" className="text-sm text-neutral-600">
              View conference details and deadlines for this date.
            </div>
          </DialogHeader>
          <div className="space-y-4">
            {selectedDayEvents.events.deadlines.length > 0 && (
              <div>
                <h3 className="text-lg font-semibold text-red-500 mb-3">Submission Deadlines</h3>
                <div className="space-y-4">
                  {selectedDayEvents.events.deadlines.map(conf => (
                    <div key={conf.id || conf.title}>
                      {renderEventDetails(conf)}
                    </div>
                  ))}
                </div>
              </div>
            )}
            {selectedDayEvents.events.conferences.length > 0 && (
              <div>
                <h3 className="text-lg font-semibold text-purple-600 mb-3">Conferences</h3>
                <div className="space-y-4">
                  {selectedDayEvents.events.conferences.map(conf => (
                    <div key={conf.id || conf.title}>
                      {renderEventDetails(conf)}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default CalendarPage;
