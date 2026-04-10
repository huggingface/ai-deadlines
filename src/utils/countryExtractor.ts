/**
 * Extracts country from a conference place string
 */
export function extractCountry(place: string): string | null {
  if (!place) return null;
  
  // Extract the last part after the last comma, which is typically the country
  const parts = place.split(',');
  const country = parts[parts.length - 1].trim();
  
  // Handle special cases like "USA" which might appear in different forms
  if (['USA', 'U.S.A.', 'United States', 'United States of America'].includes(country)) {
    return 'USA';
  }
  
  // Handle "UK" variations
  if (['UK', 'U.K.', 'United Kingdom', 'England', 'Scotland', 'Wales'].includes(country)) {
    return 'UK';
  }
  
  // For places without commas, try to extract known countries
  if (parts.length === 1) {
    const knownCountries = [
      'USA', 'Canada', 'China', 'Japan', 'Germany', 'France', 'UK', 'Italy', 
      'Spain', 'Australia', 'Brazil', 'India', 'Singapore', 'South Korea', 
      'Netherlands', 'Sweden', 'Switzerland', 'Belgium', 'Austria', 'Portugal',
      'UAE', 'Thailand', 'Hawaii', 'Russia', 'Lithuania'
    ];
    
    for (const country of knownCountries) {
      if (place.includes(country)) {
        return country;
      }
    }
  }
  
  return country;
}

/**
 * Gets all unique countries from conferences data
 */
export function getAllCountries(conferences: Array<{ country?: string }>): string[] {
  if (!Array.isArray(conferences)) return [];
  
  const countries = new Set<string>();
  
  conferences.forEach(conf => {
    if (conf.country) {
      countries.add(conf.country);
    }
  });
  
  return Array.from(countries).sort();
} 