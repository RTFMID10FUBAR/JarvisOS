package com.jarvisos.ghostmesh.data

val OSINT_CATEGORIES: List<OsintCategory> = listOf(
    OsintCategory(
        id = "search",
        name = "Search Engines",
        tools = listOf(
            OsintTool("DuckDuckGo", "Privacy-first search engine with .onion version", "https://duckduckgo.com", listOf("free", "search")),
            OsintTool("Marginalia", "Independent web index focused on non-commercial content", "https://search.marginalia.nu", listOf("free", "search")),
            OsintTool("Shodan", "Search engine for internet-connected devices and services", "https://shodan.io", listOf("paid", "network", "iot")),
            OsintTool("Censys", "Internet-wide scanning for hosts, certificates, and services", "https://censys.io", listOf("freemium", "network")),
            OsintTool("Grep.app", "Search across half a million git repos with regex", "https://grep.app", listOf("free", "code")),
            OsintTool("PublicWWW", "Source code search engine — find sites by HTML/JS snippet", "https://publicwww.com", listOf("freemium", "web")),
        )
    ),
    OsintCategory(
        id = "people",
        name = "People & Identity",
        tools = listOf(
            OsintTool("Sherlock", "Hunt down social media accounts by username", "https://github.com/sherlock-project/sherlock", listOf("free", "username", "oss")),
            OsintTool("WhatsMyName", "Username enumeration across 600+ sites", "https://whatsmyname.app", listOf("free", "username")),
            OsintTool("HaveIBeenPwned", "Check if email/password appeared in data breaches", "https://haveibeenpwned.com", listOf("free", "breach", "email")),
            OsintTool("Hunter.io", "Find professional email addresses by domain", "https://hunter.io", listOf("freemium", "email")),
            OsintTool("Pipl", "Deep web people search aggregator", "https://pipl.com", listOf("paid", "people")),
            OsintTool("LinkedIn", "Professional network — search by name, company, location", "https://linkedin.com", listOf("freemium", "professional")),
            OsintTool("Spokeo", "People search using name, address, phone, email", "https://spokeo.com", listOf("paid", "people")),
            OsintTool("Intelius", "Public records search (US)", "https://intelius.com", listOf("paid", "people")),
        )
    ),
    OsintCategory(
        id = "domain",
        name = "Domains & DNS",
        tools = listOf(
            OsintTool("ViewDNS.info", "DNS records, WHOIS, IP history, reverse DNS", "https://viewdns.info", listOf("free", "dns", "whois")),
            OsintTool("DNSDumpster", "DNS reconnaissance — subdomains, MX, TXT, host map", "https://dnsdumpster.com", listOf("free", "dns")),
            OsintTool("Crt.sh", "Certificate transparency log search — find subdomains", "https://crt.sh", listOf("free", "ssl", "subdomain")),
            OsintTool("SecurityTrails", "Historical DNS, subdomain enumeration, associated IPs", "https://securitytrails.com", listOf("freemium", "dns")),
            OsintTool("Amass", "In-depth attack surface mapping and asset discovery", "https://github.com/owasp-amass/amass", listOf("free", "oss", "subdomain")),
            OsintTool("Subfinder", "Fast passive subdomain enumeration tool", "https://github.com/projectdiscovery/subfinder", listOf("free", "oss", "subdomain")),
            OsintTool("WHOIS Lookup", "Domain registration information and history", "https://who.is", listOf("free", "whois")),
            OsintTool("DomainTools", "WHOIS history, reverse IP, hosting history", "https://domaintools.com", listOf("paid", "whois", "dns")),
        )
    ),
    OsintCategory(
        id = "ip_network",
        name = "IP & Network",
        tools = listOf(
            OsintTool("Shodan", "Scan results for any IP — open ports, banners, CVEs", "https://shodan.io", listOf("paid", "network")),
            OsintTool("GreyNoise", "Context on IP noise — scanners, crawlers, bots", "https://viz.greynoise.io", listOf("freemium", "threat-intel")),
            OsintTool("AbuseIPDB", "IP reputation database — reports of malicious activity", "https://abuseipdb.com", listOf("free", "threat-intel")),
            OsintTool("IPinfo.io", "IP geolocation, ASN, carrier, privacy detection", "https://ipinfo.io", listOf("freemium", "geo")),
            OsintTool("BGP.he.net", "BGP routing data, ASN info, IP prefix lookups", "https://bgp.he.net", listOf("free", "network")),
            OsintTool("Censys", "Internet-wide port scan data and certificate search", "https://search.censys.io", listOf("freemium", "network")),
            OsintTool("Wigle", "Wi-Fi network database — geolocation of BSSIDs", "https://wigle.net", listOf("free", "wifi")),
        )
    ),
    OsintCategory(
        id = "social",
        name = "Social Media",
        tools = listOf(
            OsintTool("Social Searcher", "Real-time social media search across platforms", "https://social-searcher.com", listOf("freemium", "social")),
            OsintTool("Twint", "Twitter/X scraper — no API key required", "https://github.com/twintproject/twint", listOf("free", "oss", "twitter")),
            OsintTool("IntelX", "Historical data — social media, pastes, dark web leaks", "https://intelx.io", listOf("freemium", "search")),
            OsintTool("Reddit Search", "Search Reddit posts/comments with Pushshift", "https://camas.unddit.com", listOf("free", "social")),
            OsintTool("Osint.industries", "Reverse email/phone search across social platforms", "https://osint.industries", listOf("freemium", "social")),
            OsintTool("Google Dorks", "Advanced Google operators for targeted search", "https://www.exploit-db.com/google-hacking-database", listOf("free", "search")),
        )
    ),
    OsintCategory(
        id = "images",
        name = "Images & Media",
        tools = listOf(
            OsintTool("Google Images", "Reverse image search to find origin and matches", "https://images.google.com", listOf("free", "image")),
            OsintTool("Yandex Images", "Best reverse image search for faces and details", "https://yandex.com/images", listOf("free", "image")),
            OsintTool("TinEye", "Reverse image search with exact match detection", "https://tineye.com", listOf("free", "image")),
            OsintTool("PimEyes", "Face recognition reverse image search", "https://pimeyes.com", listOf("paid", "image", "face")),
            OsintTool("FotoForensics", "JPEG error level analysis and metadata extraction", "https://fotoforensics.com", listOf("free", "image", "forensics")),
            OsintTool("Jeffrey's Exif Viewer", "Online EXIF metadata viewer for images", "https://exifdata.com", listOf("free", "metadata")),
            OsintTool("InVID / WeVerify", "Video/image verification and metadata toolkit", "https://weverify.eu/tools", listOf("free", "video", "verification")),
        )
    ),
    OsintCategory(
        id = "threat_intel",
        name = "Threat Intelligence",
        tools = listOf(
            OsintTool("VirusTotal", "Scan files, URLs, IPs, and hashes against 70+ AV engines", "https://virustotal.com", listOf("free", "malware", "reputation")),
            OsintTool("AlienVault OTX", "Open threat exchange — IoCs, threat feeds, pulses", "https://otx.alienvault.com", listOf("free", "threat-intel")),
            OsintTool("URLScan.io", "Sandbox URLs — full screenshot, DOM, network requests", "https://urlscan.io", listOf("free", "url", "sandbox")),
            OsintTool("IBM X-Force", "Threat intelligence for IPs, URLs, malware hashes", "https://exchange.xforce.ibmcloud.com", listOf("free", "threat-intel")),
            OsintTool("Hybrid Analysis", "Free malware sandbox analysis (Falcon Sandbox)", "https://hybrid-analysis.com", listOf("free", "malware", "sandbox")),
            OsintTool("MalwareBazaar", "Upload/search malware samples and hashes", "https://bazaar.abuse.ch", listOf("free", "malware")),
            OsintTool("Talos Intelligence", "Cisco threat intelligence on IPs, domains, hashes", "https://talosintelligence.com", listOf("free", "threat-intel")),
            OsintTool("Pulsedive", "Threat intelligence enrichment — IoC search and feeds", "https://pulsedive.com", listOf("freemium", "threat-intel")),
        )
    ),
    OsintCategory(
        id = "archive",
        name = "Archives & Caches",
        tools = listOf(
            OsintTool("Wayback Machine", "Internet Archive — browse historical snapshots of any URL", "https://web.archive.org", listOf("free", "archive")),
            OsintTool("CachedView", "View Google, Archive.org, and Bing cached pages", "https://cachedview.nl", listOf("free", "cache")),
            OsintTool("Archive.ph", "On-demand page archiving and snapshot sharing", "https://archive.ph", listOf("free", "archive")),
            OsintTool("Timetravel", "Multi-source web archive aggregator (Memento API)", "https://timetravel.mementoweb.org", listOf("free", "archive")),
        )
    ),
    OsintCategory(
        id = "leaks",
        name = "Leaks & Breach Data",
        tools = listOf(
            OsintTool("HaveIBeenPwned", "Breach search by email — 12B+ accounts", "https://haveibeenpwned.com", listOf("free", "breach")),
            OsintTool("DeHashed", "Deep breach search — email, username, IP, name, phone", "https://dehashed.com", listOf("paid", "breach")),
            OsintTool("IntelX", "Historical breach data, pastes, and dark web search", "https://intelx.io", listOf("freemium", "breach")),
            OsintTool("Snusbase", "Breach data search by email, username, password hash", "https://snusbase.com", listOf("paid", "breach")),
            OsintTool("LeakCheck", "Email-centric breach lookup with password hinting", "https://leakcheck.io", listOf("freemium", "breach")),
        )
    ),
    OsintCategory(
        id = "frameworks",
        name = "Frameworks & Methodology",
        tools = listOf(
            OsintTool("MITRE ATT&CK", "Adversary tactics and techniques knowledge base", "https://attack.mitre.org", listOf("free", "framework")),
            OsintTool("OSINT Framework", "Categorized list of free OSINT resources and tools", "https://osintframework.com", listOf("free", "framework")),
            OsintTool("Maltego", "Link analysis and data visualization platform", "https://maltego.com", listOf("freemium", "framework", "visualization")),
            OsintTool("Recon-ng", "Full-featured web reconnaissance framework (Python)", "https://github.com/lanmaster53/recon-ng", listOf("free", "oss", "framework")),
            OsintTool("SpiderFoot", "Automated OSINT collection with 200+ modules", "https://spiderfoot.net", listOf("freemium", "oss", "framework")),
            OsintTool("TheHarvester", "Email, subdomain, and host enumeration tool", "https://github.com/laramies/theHarvester", listOf("free", "oss", "recon")),
        )
    ),
)
