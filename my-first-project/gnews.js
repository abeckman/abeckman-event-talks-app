#!/usr/bin/env node
import Parser from 'rss-parser';
import { parseArgs } from 'node:util';

const parser = new Parser();

// ANSI Colors
const RESET = "\x1b[0m";
const BOLD = "\x1b[1m";
const TITLE = "\x1b[1;37m";  // Bold White
const SOURCE = "\x1b[1;32m"; // Bold Green
const DATE = "\x1b[36m";     // Cyan
const LINK = "\x1b[4;34m";   // Underline Blue
const INDEX = "\x1b[1;33m";  // Bold Yellow
const HEADER = "\x1b[1;35m"; // Bold Magenta

const TOPICS = {
  world: 'WORLD',
  nation: 'NATION',
  business: 'BUSINESS',
  technology: 'TECHNOLOGY',
  entertainment: 'ENTERTAINMENT',
  sports: 'SPORTS',
  science: 'SCIENCE',
  health: 'HEALTH'
};

const options = {
  topic: { type: 'string', short: 't' },
  search: { type: 'string', short: 's' },
  limit: { type: 'string', short: 'l', default: '10' },
  help: { type: 'boolean', short: 'h' }
};

function printHelp() {
  console.log(`
Usage: node gnews.js [options]

Options:
  -t, --topic <name>    Filter news by topic.
                        Available topics: ${Object.keys(TOPICS).join(', ')}
  -s, --search <query>  Search articles by keyword
  -l, --limit <number>  Limit number of displayed news (default: 10)
  -h, --help            Show this help message
`);
}

async function main() {
  let values;
  try {
    const result = parseArgs({ options, allowPositionals: true });
    values = result.values;
  } catch (err) {
    console.error(`Error parsing arguments: ${err.message}`);
    printHelp();
    process.exit(1);
  }

  if (values.help) {
    printHelp();
    process.exit(0);
  }

  let url = 'https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en';
  let titleContext = 'Top Stories';

  if (values.search) {
    const query = encodeURIComponent(values.search);
    url = `https://news.google.com/rss/search?q=${query}&hl=en-US&gl=US&ceid=US:en`;
    titleContext = `Search results for '${values.search}'`;
  } else if (values.topic) {
    const topicLower = values.topic.toLowerCase();
    if (TOPICS[topicLower]) {
      const topicId = TOPICS[topicLower];
      url = `https://news.google.com/rss/headlines/section/topic/${topicId}?hl=en-US&gl=US&ceid=US:en`;
      titleContext = `Topic: ${values.topic.toUpperCase()}`;
    } else {
      console.error(`Unknown topic '${values.topic}'. Available topics: ${Object.keys(TOPICS).join(', ')}`);
      process.exit(1);
    }
  }

  const limit = parseInt(values.limit, 10);
  if (isNaN(limit) || limit <= 0) {
    console.error(`Invalid limit value: ${values.limit}. Must be a positive integer.`);
    process.exit(1);
  }

  console.log(`Fetching news from Google (${titleContext})...`);

  try {
    const feed = await parser.parseURL(url);
    if (!feed.items || feed.items.length === 0) {
      console.log('No articles found.');
      return;
    }

    const count = Math.min(feed.items.length, limit);
    console.log(`\n${HEADER}=== Google News - Latest Articles (showing {count}) ===${RESET}`.replace('{count}', count));

    for (let i = 0; i < count; i++) {
      const item = feed.items[i];
      const title = item.title || 'No Title';
      const link = item.link || '';
      
      // Google News pubDate is usually a standard ISO or RFC822 string
      let dateStr = item.pubDate || '';
      if (dateStr) {
        try {
          const dt = new Date(dateStr);
          // Format as "Jun 15, 2026 07:57 PM"
          dateStr = dt.toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            hour12: true
          });
        } catch (e) {
          // Keep raw string if parsing fails
        }
      }

      // Try to clean the title by removing the source suffix
      let cleanTitle = title;
      let sourceName = item.source?.title || '';
      
      if (!sourceName) {
        // Fallback: extract source from title (e.g. "Title - Source")
        const lastDash = title.lastIndexOf(' - ');
        if (lastDash !== -1) {
          cleanTitle = title.substring(0, lastDash);
          sourceName = title.substring(lastDash + 3);
        }
      } else {
        // If we have the source name explicitly, strip it from the title
        const suffix = ` - ${sourceName}`;
        if (cleanTitle.endsWith(suffix)) {
          cleanTitle = cleanTitle.slice(0, -suffix.length);
        }
      }

      console.log(`${INDEX}[${i + 1}]${RESET} ${TITLE}${cleanTitle}${RESET}`);
      console.log(`    Source: ${SOURCE}${sourceName || 'Unknown'}${RESET} | Date: ${DATE}${dateStr}${RESET}`);
      console.log(`    Link:   ${LINK}${link}${RESET}\n`);
    }
  } catch (err) {
    console.error(`Error fetching or parsing feed: ${err.message}`);
    process.exit(1);
  }
}

main();
