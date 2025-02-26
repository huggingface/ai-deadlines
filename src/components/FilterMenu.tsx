import { useMemo, useState } from "react";
import conferencesData from "@/data/conferences.yml";
import { Conference } from "@/types/conference";
import { Checkbox } from "./ui/checkbox";

interface FilterMenuProps {
  isOpen: boolean;
  onClose: () => void;
  selectedCountries: Set<string>;
  onCountriesChange: (countries: Set<string>) => void;
}

interface CountryFilterProps {
  countries: string[];
  selectedCountries: Set<string>;
  onSelect: (countries: Set<string>) => void;
  onClose: () => void;
}


/**
 * CountryFilter component
 * This component is used to display the list of countries and allow the user to select them
 * */
const CountryFilter = ({
  countries,
  selectedCountries,
  onSelect,
  onClose,
}: CountryFilterProps) => {


  const handleCountryToggle = (country: string) => {
    const newCountries = new Set(selectedCountries);
    if (newCountries.has(country)) {
      newCountries.delete(country);
    } else {
      newCountries.add(country);
    }
    onSelect(newCountries);
  };

  return (
    <div className="p-4 space-y-3 max-h-60 overflow-y-auto">
      <div className="flex justify-between items-center mb-4">
        <button
          className="text-xs text-blue-500 hover:underline"
          onClick={onClose}
        >
          &larr; Back
        </button>
        <button
          className="text-xs text-red-500 hover:underline"
          onClick={() => onSelect(new Set())}
        >
          Clear
        </button>
      </div>

      <ul className="space-y-2">
        {countries.map((country) => (
          <li
            key={country}
            className="flex items-center justify-between cursor-pointer hover:bg-gray-50 p-2 rounded"
            onClick={() => handleCountryToggle(country)}
          >
            <span>{country}</span>
            <Checkbox
              // type="checkbox"
              className="h-4 w-4 text-blue-500 rounded border-gray-300"
              checked={selectedCountries.has(country)}
              onChange={() => handleCountryToggle(country)}
            />
          </li>
        ))}
      </ul>
    </div>
  );
};

export const getCountry = (place: string) => {
  return place?.split(",")?.pop().trim().replace(/\.$/, "");
}


/**
 * FilterMenu component
 * This component is used to display the filter menu
 * */
const FilterMenu = ({
  isOpen,
  onClose,
  selectedCountries,
  onCountriesChange,
}: FilterMenuProps) => {
  const [activeFilter, setActiveFilter] = useState<string>("");

  // Clear countries function
  const clearFilters = () => {
    onCountriesChange(new Set());
    setActiveFilter(null);
  };

  // Extract countries from RAW data (not filtered data)
  const countries = useMemo(() => {
    if (!Array.isArray(conferencesData)) return [];

    const places: string[] = conferencesData
    /*
    Extract country info from place.
    if place is "City, ..., Country", we split by "," and get the last element
    if place is "Country", we just get the place
    if place ends with ".", we remove it
    place cannot be empty as We are assuming we require place to be present
    */
      .map((conf: Conference) => getCountry(conf.place))
      .filter((place): place is string => !!place); // Remove undefined/empty

    return Array.from(new Set(places)).sort(); // Unique + sorted
  }, [conferencesData]); // Only recompute when raw data changes

  return (
    <div
      className={`absolute bg-white shadow-lg rounded-lg border transition-all duration-300 ${
        isOpen
          ? "opacity-100 scale-100"
          : "opacity-0 scale-95 pointer-events-none"
      }`}
      style={{ top: "100%", left: "-100%", width: "250px" }}
    >
      {/* Header */}
      <div className="flex justify-between items-center p-4 border-b">
        <h2 className="text-sm font-semibold">Add Filters</h2>
        <button
          className="text-xs text-green-500 hover:underline"
          onClick={() => {
            setActiveFilter(null);
            onClose();
            clearFilters();
          }}
        >
          Clear All
        </button>
      </div>

      {!activeFilter ? (
        <div className="p-4 space-y-3">
          <div
            className="flex justify-between items-center cursor-pointer hover:bg-gray-100 p-2 rounded"
            onClick={() => setActiveFilter("country")}
          >
            <span>
              Country{" "}
              {selectedCountries.size > 0 && `(${selectedCountries.size})`}
            </span>
            <span className="text-gray-400">&rarr;</span>
          </div>
        </div>
      ) : activeFilter === "country" ? (
        <CountryFilter
          countries={countries}
          selectedCountries={selectedCountries}
          onSelect={onCountriesChange}
          onClose={() => setActiveFilter(null)}
        />
      ) : null}
    </div>
  );
};

export default FilterMenu;
