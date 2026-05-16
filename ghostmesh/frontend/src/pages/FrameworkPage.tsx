import { useState } from 'react';
import {
  Network,
  ExternalLink,
  Search,
  ChevronDown,
  ChevronRight,
  Key,
  Info,
} from 'lucide-react';
import { SectionHeader } from '../components';
import type { OsintTool, OsintCategory } from '../types';

// ---------------------------------------------------------------------------
// Full tool catalog
// ---------------------------------------------------------------------------

const CATEGORIES: (OsintCategory & { color: string })[] = [
  {
    id: 'usernames',
    name: 'Usernames',
    icon: 'user',
    color: '#2f81f7',
    tools: [
      { id: 'namechk',     name: 'Namechk',         description: 'Check username availability across hundreds of social networks and domains.',    url: 'https://namechk.com',                     requires_key: false, mode: 'passive', status: 'available' },
      { id: 'sherlock',    name: 'Sherlock',          description: 'Hunt down social media accounts by username across 400+ platforms (CLI tool).', url: 'https://github.com/sherlock-project/sherlock', requires_key: false, mode: 'passive', status: 'available' },
      { id: 'whatsmyname', name: 'WhatsMyName',       description: 'Web-based username enumeration across social networks and forums.',              url: 'https://whatsmyname.app',                 requires_key: false, mode: 'passive', status: 'available' },
      { id: 'knowem',      name: 'KnowEm',            description: 'Check a username on over 550 popular and emerging social networks.',             url: 'https://knowem.com',                      requires_key: false, mode: 'passive', status: 'available' },
    ],
  },
  {
    id: 'domains_dns',
    name: 'Domains & DNS',
    icon: 'globe',
    color: '#39d353',
    tools: [
      { id: 'dnsdumpster',     name: 'DNSDumpster',       description: 'Free domain research tool for discovering hosts related to a domain.',              url: 'https://dnsdumpster.com',               requires_key: false, mode: 'passive', status: 'available'    },
      { id: 'viewdns',         name: 'ViewDNS.info',      description: 'Reverse IP lookups, DNS records, port scan and other domain research tools.',      url: 'https://viewdns.info',                  requires_key: false, mode: 'passive', status: 'available'    },
      { id: 'securitytrails',  name: 'SecurityTrails',    description: 'Historical DNS records, subdomains, IP history and domain reputation data.',       url: 'https://securitytrails.com',            requires_key: true,  mode: 'passive', status: 'key_required' },
      { id: 'shodan',          name: 'Shodan',             description: 'Search engine for Internet-connected devices, services, banners, and CVEs.',       url: 'https://shodan.io',                     requires_key: true,  mode: 'passive', status: 'key_required' },
      { id: 'whois_dt',        name: 'Whois DomainTools',  description: 'Comprehensive WHOIS history, domain ownership records and registrar data.',        url: 'https://whois.domaintools.com',         requires_key: false, mode: 'passive', status: 'available'    },
    ],
  },
  {
    id: 'email',
    name: 'Email',
    icon: 'mail',
    color: '#bc8cff',
    tools: [
      { id: 'hunterio',   name: 'Hunter.io',      description: 'Find and verify professional email addresses for any company or domain.',     url: 'https://hunter.io',                     requires_key: true,  mode: 'passive', status: 'key_required' },
      { id: 'phonebook',  name: 'Phonebook.cz',   description: 'Email and domain intelligence search powered by leaked data and OSINT.',      url: 'https://phonebook.cz',                  requires_key: false, mode: 'passive', status: 'available'    },
      { id: 'holehe',     name: 'Holehe',          description: 'Check if an email is associated with accounts on 120+ sites (CLI).',         url: 'https://github.com/megadose/holehe',    requires_key: false, mode: 'passive', status: 'available'    },
      { id: 'h8mail',     name: 'h8mail',          description: 'Email OSINT and breach hunting tool using multiple data sources (CLI).',      url: 'https://github.com/khast3x/h8mail',    requires_key: false, mode: 'passive', status: 'available'    },
      { id: 'emailhippo', name: 'EmailHippo',      description: 'Email verification service that checks MX, SMTP and mailbox existence.',     url: 'https://tools.emailhippo.com',          requires_key: true,  mode: 'passive', status: 'key_required' },
    ],
  },
  {
    id: 'phone',
    name: 'Phone Numbers',
    icon: 'phone',
    color: '#f0a732',
    tools: [
      { id: 'numverify',   name: 'NumVerify',    description: 'Phone number validation, location and carrier lookup via REST API.',          url: 'https://numverify.com',               requires_key: true,  mode: 'passive', status: 'key_required' },
      { id: 'truecaller',  name: 'Truecaller',   description: 'Identify unknown callers and search phone number ownership (manual).',        url: 'https://truecaller.com',              requires_key: true,  mode: 'passive', status: 'key_required' },
      { id: 'phoneinfoga', name: 'PhoneInfoga',  description: 'Advanced information gathering tool for phone numbers via OSINT (CLI).',     url: 'https://github.com/sundowndev/phoneinfoga', requires_key: false, mode: 'passive', status: 'available' },
    ],
  },
  {
    id: 'public_records',
    name: 'Public Records',
    icon: 'book',
    color: '#58a6ff',
    tools: [
      { id: 'pacer',         name: 'PACER',            description: 'Public Access to Court Electronic Records — US federal court documents.',    url: 'https://pacer.uscourts.gov',         requires_key: false, mode: 'passive', status: 'available' },
      { id: 'courtlistener', name: 'CourtListener',    description: 'Free, searchable, real-time database of US court opinions and dockets.',      url: 'https://courtlistener.com',          requires_key: false, mode: 'passive', status: 'available' },
      { id: 'opencorporates', name: 'OpenCorporates',  description: 'The largest open database of companies in the world — 200+ jurisdictions.',   url: 'https://opencorporates.com',         requires_key: false, mode: 'passive', status: 'available' },
      { id: 'occrp_aleph',   name: 'OCCRP Aleph',      description: 'Investigative data platform with leaked and public datasets from 140+ countries.', url: 'https://aleph.occrp.org',       requires_key: false, mode: 'passive', status: 'available' },
    ],
  },
  {
    id: 'breach_check',
    name: 'Breach & Leak Databases',
    icon: 'shield',
    color: '#f85149',
    tools: [
      { id: 'hibp',            name: 'HaveIBeenPwned',   description: 'Check if email addresses or passwords appear in known data breaches.',      url: 'https://haveibeenpwned.com',         requires_key: true,  mode: 'passive', status: 'key_required' },
      { id: 'leakcheck',       name: 'LeakCheck',         description: 'Search leaked databases by email, username, password hash or keyword.',     url: 'https://leakcheck.io',               requires_key: true,  mode: 'passive', status: 'key_required' },
      { id: 'breachdirectory', name: 'BreachDirectory',   description: 'Search exposed credentials across data breaches with password exposure.',   url: 'https://breachdirectory.org',        requires_key: false, mode: 'passive', status: 'available'    },
    ],
  },
  {
    id: 'social_profiles',
    name: 'Social Profiles',
    icon: 'users',
    color: '#e6edf3',
    tools: [
      { id: 'linkedin',  name: 'LinkedIn',      description: 'Search professional profiles, company pages and employment history (manual).',   url: 'https://linkedin.com',               requires_key: false, mode: 'passive', status: 'available' },
      { id: 'twitter',   name: 'Twitter / X',   description: 'Search tweets, accounts and social connections using Advanced Search (manual).', url: 'https://x.com/search-advanced',      requires_key: false, mode: 'passive', status: 'available' },
      { id: 'instagram', name: 'Instagram',     description: 'Browse public profiles and hashtags for OSINT leads (manual browsing).',         url: 'https://instagram.com',              requires_key: false, mode: 'passive', status: 'available' },
      { id: 'pipl',      name: 'Pipl',           description: 'Deep web people search engine aggregating social, professional and public data.', url: 'https://pipl.com',                   requires_key: true,  mode: 'passive', status: 'key_required' },
    ],
  },
  {
    id: 'github_code',
    name: 'GitHub & Code Search',
    icon: 'code',
    color: '#6e7681',
    tools: [
      { id: 'github_search', name: 'GitHub Search',  description: 'Search public repositories, commits, issues and code across GitHub.',           url: 'https://github.com/search',           requires_key: false, mode: 'passive', status: 'available' },
      { id: 'grepapp',       name: 'Grep.app',        description: 'Search across 500k+ public git repos with regex support in real-time.',         url: 'https://grep.app',                    requires_key: false, mode: 'passive', status: 'available' },
      { id: 'searchcode',    name: 'SearchCode',      description: 'Code search engine indexing billions of lines across open source projects.',     url: 'https://searchcode.com',              requires_key: false, mode: 'passive', status: 'available' },
      { id: 'gitlab_search', name: 'GitLab Search',  description: 'Search public repositories on GitLab for credentials and sensitive data.',       url: 'https://gitlab.com/explore',          requires_key: false, mode: 'passive', status: 'available' },
    ],
  },
  {
    id: 'images',
    name: 'Images & Reverse Search',
    icon: 'image',
    color: '#39d353',
    tools: [
      { id: 'tineye',       name: 'TinEye',           description: 'Reverse image search engine that finds where an image appears on the web.',    url: 'https://tineye.com',                  requires_key: true,  mode: 'passive', status: 'key_required' },
      { id: 'google_img',   name: 'Google Images',    description: 'Reverse image search using Google Lens to find similar images (manual).',      url: 'https://images.google.com',           requires_key: false, mode: 'passive', status: 'available'    },
      { id: 'yandex_img',   name: 'Yandex Images',   description: 'Russian reverse image search — often finds results that Google misses.',         url: 'https://yandex.com/images',           requires_key: false, mode: 'passive', status: 'available'    },
      { id: 'pimeyes',      name: 'PimEyes',           description: 'Face recognition reverse image search engine for finding faces online.',       url: 'https://pimeyes.com',                 requires_key: true,  mode: 'passive', status: 'key_required' },
    ],
  },
  {
    id: 'maps_location',
    name: 'Maps & Geolocation',
    icon: 'map',
    color: '#f0a732',
    tools: [
      { id: 'gmaps',     name: 'Google Maps',      description: 'Satellite imagery, street view and location intelligence for geolocation OSINT.',    url: 'https://maps.google.com',             requires_key: false, mode: 'passive', status: 'available' },
      { id: 'osm',       name: 'OpenStreetMap',    description: 'Free, community-built world map with detailed geographic data and history.',          url: 'https://openstreetmap.org',           requires_key: false, mode: 'passive', status: 'available' },
      { id: 'overpass',  name: 'Overpass Turbo',   description: 'Query and extract specific geographic data from OpenStreetMap via Overpass API.',    url: 'https://overpass-turbo.eu',           requires_key: false, mode: 'passive', status: 'available' },
      { id: 'geonames',  name: 'GeoNames',         description: 'Free geographical database of over 11 million geographic names and features.',       url: 'https://geonames.org',                requires_key: false, mode: 'passive', status: 'available' },
    ],
  },
  {
    id: 'business',
    name: 'Business & Corporate',
    icon: 'briefcase',
    color: '#58a6ff',
    tools: [
      { id: 'opencorp',       name: 'OpenCorporates',    description: 'Global company registry data covering 200+ jurisdictions and 200M+ companies.',   url: 'https://opencorporates.com',          requires_key: false, mode: 'passive', status: 'available' },
      { id: 'companies_house', name: 'Companies House',  description: 'UK official company registry with filings, ownership and financial data.',         url: 'https://find-and-update.company-information.service.gov.uk', requires_key: false, mode: 'passive', status: 'available' },
      { id: 'sec_edgar',      name: 'SEC EDGAR',          description: 'US Securities and Exchange Commission filings, 10-K reports and ownership data.',  url: 'https://www.sec.gov/edgar/search',    requires_key: false, mode: 'passive', status: 'available' },
      { id: 'crunchbase',     name: 'Crunchbase',         description: 'Startup and investment data including funding rounds, acquisitions and founders.',  url: 'https://crunchbase.com',              requires_key: false, mode: 'passive', status: 'available' },
    ],
  },
  {
    id: 'archives',
    name: 'Archives & Caching',
    icon: 'archive',
    color: '#8b949e',
    tools: [
      { id: 'wayback',     name: 'Wayback Machine',  description: 'Access billions of historical web page snapshots archived by the Internet Archive.', url: 'https://web.archive.org',            requires_key: false, mode: 'passive', status: 'available' },
      { id: 'cachedview',  name: 'CachedView',       description: 'View cached versions of pages from Google Cache and the Wayback Machine.',           url: 'https://cachedview.nl',              requires_key: false, mode: 'passive', status: 'available' },
      { id: 'archive_ph',  name: 'Archive.ph',       description: 'Create and access permanent web page snapshots, useful for preserving evidence.',      url: 'https://archive.ph',                 requires_key: false, mode: 'passive', status: 'available' },
      { id: 'commoncrawl', name: 'Common Crawl',     description: 'Petabyte-scale web crawl data available as open datasets for research and OSINT.',    url: 'https://commoncrawl.org',            requires_key: false, mode: 'passive', status: 'available' },
    ],
  },
  {
    id: 'metadata',
    name: 'Metadata Extraction',
    icon: 'file-search',
    color: '#6e7681',
    tools: [
      { id: 'exiftool',      name: 'ExifTool',            description: 'Industry-standard CLI tool for reading and writing metadata in any file format.', url: 'https://exiftool.org',               requires_key: false, mode: 'passive', status: 'available' },
      { id: 'foca',          name: 'FOCA',                 description: 'Fingerprint organizations through document metadata and network analysis (tool).', url: 'https://github.com/ElevenPaths/FOCA', requires_key: false, mode: 'passive', status: 'available' },
      { id: 'jeffrey_exif',  name: "Jeffrey's Exif Viewer", description: 'Web-based EXIF viewer for images — shows GPS, camera and shooting data.',      url: 'http://exif.regex.info/exif.cgi',    requires_key: false, mode: 'passive', status: 'available' },
    ],
  },
  {
    id: 'cve_security',
    name: 'CVE & Security',
    icon: 'shield-alert',
    color: '#f85149',
    tools: [
      { id: 'shodan_cve',  name: 'Shodan CVE',     description: 'Search Shodan for hosts vulnerable to specific CVEs using the Shodan CVE API.',   url: 'https://cvedb.shodan.io',             requires_key: true,  mode: 'passive', status: 'key_required' },
      { id: 'nvd',         name: 'NVD (NIST)',      description: 'National Vulnerability Database — authoritative CVE details and CVSS scores.',    url: 'https://nvd.nist.gov/vuln/search',    requires_key: false, mode: 'passive', status: 'available'    },
      { id: 'cvedetails',  name: 'CVEdetails',      description: 'Vulnerability database with searchable CVEs, software statistics and timelines.',  url: 'https://cvedetails.com',              requires_key: false, mode: 'passive', status: 'available'    },
      { id: 'exploitdb',   name: 'Exploit-DB',      description: 'Public exploit archive and proof-of-concept database maintained by Offensive Security.', url: 'https://exploit-db.com',         requires_key: false, mode: 'passive', status: 'available'    },
      { id: 'vulndb',      name: 'VulnDB',           description: 'Commercial vulnerability intelligence database with deeper CVE context and analysis.', url: 'https://vulndb.cyberriskanalytics.com', requires_key: true, mode: 'passive', status: 'key_required' },
    ],
  },
];

// ---------------------------------------------------------------------------
// Helper: mode badge colors
// ---------------------------------------------------------------------------

const MODE_STYLE: Record<string, { bg: string; text: string }> = {
  passive: { bg: 'rgba(57,211,83,0.12)',  text: 'var(--gm-teal)'   },
  active:  { bg: 'rgba(248,81,73,0.12)',  text: 'var(--gm-red)'    },
};

// ---------------------------------------------------------------------------
// ToolCard
// ---------------------------------------------------------------------------

interface ToolCardProps {
  tool: OsintTool;
  categoryColor: string;
}

function ToolCard({ tool, categoryColor }: ToolCardProps) {
  const modeStyle = MODE_STYLE[tool.mode] ?? MODE_STYLE.passive;
  return (
    <div
      className="rounded-lg border flex flex-col gap-2 transition-all duration-150"
      style={{
        background: 'var(--gm-bg-panel)',
        borderColor: 'var(--gm-border)',
        padding: '0.75rem 0.875rem',
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLDivElement).style.borderColor = categoryColor;
        (e.currentTarget as HTMLDivElement).style.background = 'var(--gm-bg-hover)';
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLDivElement).style.borderColor = 'var(--gm-border)';
        (e.currentTarget as HTMLDivElement).style.background = 'var(--gm-bg-panel)';
      }}
    >
      {/* Top row: name + badges + link */}
      <div className="flex items-start gap-2 min-w-0">
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-1.5 mb-1">
            <span
              className="text-sm font-semibold"
              style={{ color: 'var(--gm-text-primary)' }}
            >
              {tool.name}
            </span>

            {/* Mode badge */}
            <span
              className="gm-badge text-xs capitalize"
              style={{ background: modeStyle.bg, color: modeStyle.text, fontSize: '10px' }}
            >
              {tool.mode}
            </span>

            {/* API key badge */}
            {tool.requires_key && (
              <span
                className="gm-badge text-xs flex items-center gap-1"
                style={{ background: 'rgba(240,167,50,0.12)', color: 'var(--gm-yellow)', fontSize: '10px' }}
              >
                <Key size={9} />
                API Key
              </span>
            )}
          </div>

          <p className="text-xs leading-relaxed" style={{ color: 'var(--gm-text-secondary)' }}>
            {tool.description}
          </p>
        </div>

        {/* External link */}
        <a
          href={tool.url}
          target="_blank"
          rel="noopener noreferrer"
          className="shrink-0 gm-btn gm-btn-secondary text-xs"
          style={{ padding: '4px 10px', fontSize: '11px' }}
          onClick={(e) => e.stopPropagation()}
        >
          <ExternalLink size={11} />
          Open
        </a>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// CategorySection
// ---------------------------------------------------------------------------

interface CategorySectionProps {
  category: (typeof CATEGORIES)[number];
  filteredTools: OsintTool[];
  expanded: boolean;
  onToggle: () => void;
}

function CategorySection({ category, filteredTools, expanded, onToggle }: CategorySectionProps) {
  if (filteredTools.length === 0) return null;

  return (
    <div className="gm-card" style={{ padding: '0' }}>
      {/* Header */}
      <button
        className="w-full flex items-center gap-3 text-left transition-colors"
        style={{ padding: '0.875rem 1rem' }}
        onClick={onToggle}
      >
        {/* Color bar */}
        <div
          className="rounded-sm shrink-0"
          style={{ width: 4, height: 18, background: category.color }}
        />

        <span className="text-sm font-semibold flex-1" style={{ color: 'var(--gm-text-primary)' }}>
          {category.name}
        </span>

        {/* Tool count */}
        <span
          className="gm-badge text-xs"
          style={{ background: 'var(--gm-bg-hover)', color: 'var(--gm-text-muted)', fontSize: '11px' }}
        >
          {filteredTools.length} tool{filteredTools.length !== 1 ? 's' : ''}
        </span>

        {/* Chevron */}
        {expanded ? (
          <ChevronDown size={14} style={{ color: 'var(--gm-text-muted)' }} />
        ) : (
          <ChevronRight size={14} style={{ color: 'var(--gm-text-muted)' }} />
        )}
      </button>

      {/* Tools grid */}
      {expanded && (
        <div
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2"
          style={{ padding: '0 1rem 1rem' }}
        >
          {filteredTools.map((tool) => (
            <ToolCard key={tool.id} tool={tool} categoryColor={category.color} />
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// FrameworkPage
// ---------------------------------------------------------------------------

const ALL_CATEGORY_IDS = CATEGORIES.map((c) => c.id);

export function FrameworkPage() {
  const [search, setSearch] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(
    new Set(ALL_CATEGORY_IDS),
  );

  function toggleCategory(id: string) {
    setExpandedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function expandAll() {
    setExpandedCategories(new Set(ALL_CATEGORY_IDS));
  }

  function collapseAll() {
    setExpandedCategories(new Set());
  }

  const query = search.toLowerCase().trim();

  const visibleCategories = CATEGORIES.filter((cat) => {
    if (selectedCategory !== 'all' && cat.id !== selectedCategory) return false;
    return true;
  }).map((cat) => ({
    ...cat,
    filteredTools: cat.tools.filter((t) => {
      if (!query) return true;
      return (
        t.name.toLowerCase().includes(query) ||
        t.description.toLowerCase().includes(query)
      );
    }),
  }));

  const totalVisible = visibleCategories.reduce((n, c) => n + c.filteredTools.length, 0);

  return (
    <div className="max-w-5xl animate-fade-in space-y-5">
      <SectionHeader
        icon={Network}
        title="OSINT Framework"
        subtitle="Curated open source intelligence tools and resources"
        actions={
          <div className="flex gap-2">
            <button className="gm-btn gm-btn-secondary text-xs" onClick={expandAll}>
              Expand all
            </button>
            <button className="gm-btn gm-btn-secondary text-xs" onClick={collapseAll}>
              Collapse all
            </button>
          </div>
        }
      />

      {/* Search + filter */}
      <div className="flex flex-col sm:flex-row gap-3">
        {/* Search input */}
        <div className="relative flex-1">
          <Search
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none"
            style={{ color: 'var(--gm-text-muted)' }}
          />
          <input
            className="gm-input w-full"
            style={{ paddingLeft: '2.25rem' }}
            type="text"
            placeholder="Search tools by name or description…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        {/* Category filter */}
        <select
          className="gm-input"
          style={{ minWidth: '200px', cursor: 'pointer' }}
          value={selectedCategory}
          onChange={(e) => setSelectedCategory(e.target.value)}
        >
          <option value="all">All categories</option>
          {CATEGORIES.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </div>

      {/* Results summary */}
      <p className="text-xs" style={{ color: 'var(--gm-text-muted)' }}>
        Showing{' '}
        <span style={{ color: 'var(--gm-text-secondary)' }}>{totalVisible}</span>{' '}
        tool{totalVisible !== 1 ? 's' : ''} across{' '}
        <span style={{ color: 'var(--gm-text-secondary)' }}>
          {visibleCategories.filter((c) => c.filteredTools.length > 0).length}
        </span>{' '}
        categories
        {query && (
          <>
            {' '}matching{' '}
            <span className="font-mono" style={{ color: 'var(--gm-accent)' }}>
              "{query}"
            </span>
          </>
        )}
      </p>

      {/* Category sections */}
      <div className="space-y-3">
        {visibleCategories.map((cat) => (
          <CategorySection
            key={cat.id}
            category={cat}
            filteredTools={cat.filteredTools}
            expanded={expandedCategories.has(cat.id)}
            onToggle={() => toggleCategory(cat.id)}
          />
        ))}

        {totalVisible === 0 && (
          <div
            className="gm-card flex flex-col items-center justify-center py-16 text-center"
          >
            <Search size={24} className="mb-3" style={{ color: 'var(--gm-text-muted)' }} />
            <p className="text-sm font-semibold mb-1" style={{ color: 'var(--gm-text-primary)' }}>
              No tools found
            </p>
            <p className="text-sm" style={{ color: 'var(--gm-text-secondary)' }}>
              Try a different search term or category filter.
            </p>
          </div>
        )}
      </div>

      {/* Legal footer */}
      <div
        className="flex items-start gap-3 rounded-lg border px-4 py-3 text-sm"
        style={{ background: 'rgba(47,129,247,0.05)', borderColor: 'rgba(47,129,247,0.2)' }}
      >
        <Info size={14} className="shrink-0 mt-0.5" style={{ color: 'var(--gm-accent)' }} />
        <p style={{ color: 'var(--gm-text-secondary)', margin: 0, lineHeight: 1.6 }}>
          <span className="font-semibold" style={{ color: 'var(--gm-text-primary)' }}>
            Legal notice:
          </span>{' '}
          Tools marked as requiring keys need accounts with the respective service. Always comply
          with each tool's terms of service and applicable laws.{' '}
          <span style={{ color: 'var(--gm-teal)' }}>Passive</span> tools are safe to use without
          target authorization;{' '}
          <span style={{ color: 'var(--gm-red)' }}>Active</span> tools require explicit written
          authorization from the target system owner.
        </p>
      </div>
    </div>
  );
}
