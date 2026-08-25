import tzLookup from "tz-lookup";

/**
 * Get the IANA timezone identifier for a given coordinate.
 * Uses tz-lookup which works offline with embedded timezone geometries.
 */
export function getTimezone(lat: number, lon: number): string {
  try {
    return tzLookup(lon, lat) || "UTC";
  } catch {
    return "UTC";
  }
}

/**
 * Format a date in a specific timezone for display.
 * Returns a string like "2:00 PM PDT" with the timezone abbreviation.
 */
export function formatInTimezone(
  date: Date,
  timezone: string,
  options: Intl.DateTimeFormatOptions = {
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  }
): string {
  try {
    return new Intl.DateTimeFormat("en-US", {
      ...options,
      timeZone: timezone,
    }).format(date);
  } catch {
    return date.toLocaleTimeString("en-US", {
      ...options,
      timeZone: "UTC",
    });
  }
}

/**
 * Get the current time in a specific timezone.
 */
export function nowInTimezone(timezone: string): Date {
  return new Date();
}

/**
 * Format a timezone offset for display (e.g., "UTC-7" or "UTC+5:30").
 */
export function formatTimezoneOffset(timezone: string, date: Date = new Date()): string {
  try {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: timezone,
      hour: "numeric",
      minute: "2-digit",
      timeZoneName: "longOffset",
    }).formatToParts(date);

    const timeZoneNamePart = parts.find((part) => part.type === "timeZoneName")?.value ?? "";
    // Parse the offset string (e.g., "GMT-7" or "GMT+5:30")
    const match = timeZoneNamePart.match(/GMT([+-]\d+)(:(\d+))?/);
    if (match) {
      const hours = match[1];
      const minutes = match[3] ? `:${match[3]}` : "";
      return `UTC${hours}${minutes}`;
    }
    return timezone;
  } catch {
    return timezone;
  }
}

/**
 * Create a datetime-local string for a given timezone and hour offset from now.
 * The datetime-local input expects local time without timezone info.
 */
export function dateTimeLocalStringInTimezone(
  timezone: string,
  hoursFromNow: number = 0
): string {
  const now = new Date();
  const targetTime = new Date(now.getTime() + hoursFromNow * 60 * 60 * 1000);

  // Format as YYYY-MM-DDTHH:mm in the target timezone
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(targetTime);

  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  const year = get("year");
  const month = get("month");
  const day = get("day");
  const hour = get("hour");
  const minute = get("minute");

  return `${year}-${month}-${day}T${hour}:${minute}`;
}