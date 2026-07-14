// Global State
let allReleases = [];
let filteredReleases = [];
let selectedReleases = new Map(); // Map of id -> release object
let activeCategory = 'all';
let searchQuery = '';

// DOM Elements
const btnRefresh = document.getElementById('btn-refresh');
const statFeatures = document.getElementById('stat-features');
const statSecurity = document.getElementById('stat-security');
const statChanges = document.getElementById('stat-changes');
const statUpdated = document.getElementById('stat-updated');
const warningBanner = document.getElementById('warning-banner');
const warningMessage = document.getElementById('warning-message');
const btnCloseWarning = document.getElementById('btn-close-warning');

const searchInput = document.getElementById('search-input');
const searchClear = document.getElementById('search-clear');
const filterPills = document.querySelectorAll('.filter-pill');

const selectedCountLabel = document.getElementById('selected-count-label');
const btnClearSelection = document.getElementById('btn-clear-selection');
const tweetTextarea = document.getElementById('tweet-textarea');
const charCounter = document.getElementById('char-counter');
const charProgressFill = document.getElementById('char-progress-fill');
const btnTweet = document.getElementById('btn-tweet');
const tweetWarningLimit = document.getElementById('tweet-warning-limit');

const feedLoading = document.getElementById('feed-loading');
const feedError = document.getElementById('feed-error');
const feedEmpty = document.getElementById('feed-empty');
const btnRetry = document.getElementById('btn-retry');
const btnResetFilters = document.getElementById('btn-reset-filters');
const releasesTimeline = document.getElementById('releases-timeline');
const feedResultsCount = document.getElementById('feed-results-count');

// Initialize Application
document.addEventListener('DOMContentLoaded', () => {
    fetchReleases();
    setupEventListeners();
});

// Setup Event Listeners
function setupEventListeners() {
    // Refresh button
    btnRefresh.addEventListener('click', () => fetchReleases(true));
    btnRetry.addEventListener('click', () => fetchReleases(true));
    
    // Warning banner close
    btnCloseWarning.addEventListener('click', () => {
        warningBanner.classList.add('hidden');
    });

    // Search input
    searchInput.addEventListener('input', (e) => {
        searchQuery = e.target.value.toLowerCase().trim();
        if (searchQuery) {
            searchClear.classList.remove('hidden');
        } else {
            searchClear.classList.add('hidden');
        }
        applyFilters();
    });

    // Clear search
    searchClear.addEventListener('click', () => {
        searchInput.value = '';
        searchQuery = '';
        searchClear.classList.add('hidden');
        applyFilters();
        searchInput.focus();
    });

    // Category filters
    filterPills.forEach(pill => {
        pill.addEventListener('click', () => {
            filterPills.forEach(p => p.classList.remove('active'));
            pill.classList.add('active');
            activeCategory = pill.dataset.filter;
            applyFilters();
        });
    });

    // Reset filters buttons
    btnResetFilters.addEventListener('click', resetAllFilters);

    // Tweet text manual input editing
    tweetTextarea.addEventListener('input', () => {
        updateCharCount(tweetTextarea.value.length);
    });

    // Tweet button
    btnTweet.addEventListener('click', sendTweet);

    // Clear selection link
    btnClearSelection.addEventListener('click', clearSelection);
}

// Fetch Release Notes from Flask API
async function fetchReleases(forceRefresh = false) {
    showLoading();
    warningBanner.classList.add('hidden');
    
    try {
        const url = forceRefresh ? '/api/releases?refresh=true' : '/api/releases';
        const response = await fetch(url);
        
        if (!response.ok) {
            throw new Error(`Server returned HTTP ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.status === 'error') {
            throw new Error(data.message);
        }
        
        allReleases = data.releases || [];
        
        // Show warnings if any (e.g. cached data warning)
        if (data.warning) {
            warningMessage.textContent = data.warning;
            warningBanner.classList.remove('hidden');
        }
        
        // Update stats
        updateStats(allReleases, data.last_updated);
        
        // Apply filters & render
        applyFilters();
        
    } catch (error) {
        console.error('Fetch error:', error);
        showError(error.message);
    }
}

// Reset Filters
function resetAllFilters() {
    searchInput.value = '';
    searchQuery = '';
    searchClear.classList.add('hidden');
    
    filterPills.forEach(p => p.classList.remove('active'));
    document.querySelector('.filter-pill[data-filter="all"]').classList.add('active');
    activeCategory = 'all';
    
    applyFilters();
}

// Update Statistics Cards
function updateStats(releases, lastUpdated) {
    statUpdated.textContent = lastUpdated || 'Just now';
    
    let featuresCount = 0;
    let securityCount = 0;
    let changesCount = 0;
    
    releases.forEach(item => {
        const typeLower = item.type.toLowerCase();
        if (typeLower.includes('feature')) {
            featuresCount++;
        } else if (typeLower.includes('security') || typeLower.includes('vulnerability')) {
            securityCount++;
        } else {
            changesCount++;
        }
    });
    
    statFeatures.textContent = featuresCount;
    statSecurity.textContent = securityCount;
    statChanges.textContent = changesCount;
}

// Apply Filters (Search and Category)
function applyFilters() {
    filteredReleases = allReleases.filter(item => {
        // 1. Category Filter
        let matchesCategory = true;
        if (activeCategory !== 'all') {
            const typeLower = item.type.toLowerCase();
            if (activeCategory === 'Other') {
                // If it doesn't match standard categories
                const standards = ['feature', 'security', 'changed', 'resolved'];
                matchesCategory = !standards.some(std => typeLower.includes(std));
            } else {
                matchesCategory = typeLower.includes(activeCategory.toLowerCase());
            }
        }
        
        // 2. Search query filter
        let matchesSearch = true;
        if (searchQuery) {
            const dateMatch = item.date.toLowerCase().includes(searchQuery);
            const typeMatch = item.type.toLowerCase().includes(searchQuery);
            const contentMatch = item.content_text.toLowerCase().includes(searchQuery);
            matchesSearch = dateMatch || typeMatch || contentMatch;
        }
        
        return matchesCategory && matchesSearch;
    });
    
    renderTimeline();
}

// Render Timeline grouped by Date
function renderTimeline() {
    releasesTimeline.innerHTML = '';
    
    if (filteredReleases.length === 0) {
        showEmpty();
        feedResultsCount.textContent = '0 updates match filters';
        return;
    }
    
    hideOverlays();
    feedResultsCount.textContent = `Showing ${filteredReleases.length} release updates`;
    
    // Group releases by date
    const grouped = {};
    filteredReleases.forEach(item => {
        if (!grouped[item.date]) {
            grouped[item.date] = [];
        }
        grouped[item.date].push(item);
    });
    
    // Render groups
    Object.keys(grouped).forEach(date => {
        const dateGroup = document.createElement('div');
        dateGroup.className = 'date-group';
        
        dateGroup.innerHTML = `
            <div class="date-header">
                <div class="date-node"></div>
                <h3 class="date-title">${date}</h3>
            </div>
            <div class="cards-container" id="cards-container-${date.replace(/\s+/g, '-')}"></div>
        `;
        
        releasesTimeline.appendChild(dateGroup);
        const container = dateGroup.querySelector(`.cards-container`);
        
        grouped[date].forEach(item => {
            const card = createReleaseCard(item);
            container.appendChild(card);
        });
    });
    
    // Initialize/Refresh Lucide Icons for dynamic content
    lucide.createIcons();
}

// Create Card Element
function createReleaseCard(item) {
    const card = document.createElement('div');
    card.id = `card-${item.id}`;
    card.className = `release-card ${selectedReleases.has(item.id) ? 'selected' : ''}`;
    
    // Determine badge class
    const typeLower = item.type.toLowerCase();
    let badgeClass = 'badge-other';
    if (typeLower.includes('feature')) badgeClass = 'badge-feature';
    else if (typeLower.includes('security')) badgeClass = 'badge-security';
    else if (typeLower.includes('changed')) badgeClass = 'badge-changed';
    else if (typeLower.includes('resolved')) badgeClass = 'badge-resolved';
    
    card.innerHTML = `
        <div class="card-header">
            <div class="card-meta">
                <div class="card-select-btn" title="Select this update for Tweet Composer">
                    <i data-lucide="check"></i>
                </div>
                <span class="category-badge ${badgeClass}">${item.type}</span>
            </div>
            
            <div class="card-actions">
                <button class="btn-icon btn-card-tweet" title="Quick Tweet this update">
                    <i data-lucide="twitter"></i>
                </button>
                <button class="btn-icon btn-card-copy" title="Copy text to clipboard">
                    <i data-lucide="copy"></i>
                </button>
                <a href="${item.link}" target="_blank" class="btn-icon btn-card-link" title="Open official GCP Release Notes">
                    <i data-lucide="external-link"></i>
                </a>
            </div>
        </div>
        
        <div class="card-body">
            ${item.content_html}
        </div>
    `;
    
    // Add Click listener for Select action
    card.querySelector('.card-select-btn').addEventListener('click', (e) => {
        e.stopPropagation();
        toggleSelectCard(item);
    });
    
    // Also toggle when clicking the card itself (excluding buttons/links/selections)
    card.addEventListener('click', (e) => {
        // Prevent toggle if clicking on links or action buttons
        if (e.target.closest('a') || e.target.closest('.card-actions') || e.target.tagName.toLowerCase() === 'a') {
            return;
        }
        toggleSelectCard(item);
    });
    
    // Quick Tweet Button
    card.querySelector('.btn-card-tweet').addEventListener('click', (e) => {
        e.stopPropagation();
        setQuickTweet(item);
    });
    
    // Copy Text Button
    card.querySelector('.btn-card-copy').addEventListener('click', (e) => {
        e.stopPropagation();
        copyToClipboard(item.content_text, card.querySelector('.btn-card-copy'));
    });
    
    return card;
}

// Toggle selection state
function toggleSelectCard(item) {
    const cardEl = document.getElementById(`card-${item.id}`);
    
    if (selectedReleases.has(item.id)) {
        selectedReleases.delete(item.id);
        if (cardEl) cardEl.classList.remove('selected');
    } else {
        selectedReleases.set(item.id, item);
        if (cardEl) cardEl.classList.add('selected');
    }
    
    updateTweetComposer();
}

// Clear Selection
function clearSelection() {
    selectedReleases.clear();
    // Remove selected class from all visible cards
    document.querySelectorAll('.release-card').forEach(card => {
        card.classList.remove('selected');
    });
    updateTweetComposer();
}

// Update Tweet Composer based on selected cards
function updateTweetComposer() {
    const count = selectedReleases.size;
    
    if (count === 0) {
        selectedCountLabel.textContent = '0 updates selected';
        btnClearSelection.classList.add('hidden');
        tweetTextarea.value = '';
        updateCharCount(0);
        return;
    }
    
    btnClearSelection.classList.remove('hidden');
    selectedCountLabel.textContent = `${count} update${count > 1 ? 's' : ''} selected`;
    
    // Sort selected releases by raw date (descending)
    const sortedSelected = Array.from(selectedReleases.values()).sort((a, b) => {
        return new Date(b.raw_date) - new Date(a.raw_date);
    });
    
    // Generate combined tweet text
    // Example: BigQuery Updates:
    // 📢 Feature (July 13): table partitioning is now GA. https://cloud.google.com/bigquery...
    let tweetText = 'Latest BigQuery Updates:\n\n';
    
    sortedSelected.forEach((item, idx) => {
        let typeEmoji = '📢';
        const typeLower = item.type.toLowerCase();
        if (typeLower.includes('security')) typeEmoji = '🛡️';
        else if (typeLower.includes('resolved') || typeLower.includes('fix')) typeEmoji = '✅';
        else if (typeLower.includes('change') || typeLower.includes('deprecat')) typeEmoji = '⚠️';
        
        // Truncate individual card text slightly if combining many to prevent giant text
        let cleanText = item.content_text;
        if (sortedSelected.length > 1 && cleanText.length > 150) {
            cleanText = cleanText.substring(0, 147) + '...';
        }
        
        tweetText += `${typeEmoji} [${item.type}] (${item.date}): ${cleanText}\n\n`;
    });
    
    // Append a shared link or standard hashtags
    tweetText += `#BigQuery #GoogleCloud`;
    
    tweetTextarea.value = tweetText;
    updateCharCount(tweetText.length);
}

// Pre-fill composer with a single update and trigger tweet
function setQuickTweet(item) {
    let typeEmoji = '📢';
    const typeLower = item.type.toLowerCase();
    if (typeLower.includes('security')) typeEmoji = '🛡️';
    else if (typeLower.includes('resolved') || typeLower.includes('fix')) typeEmoji = '✅';
    else if (typeLower.includes('change') || typeLower.includes('deprecat')) typeEmoji = '⚠️';
    
    let tweetText = `BigQuery ${typeEmoji} [${item.type}] (${item.date}):\n\n${item.content_text}\n\n`;
    tweetText += `Read more: ${item.link}\n`;
    tweetText += `#BigQuery #GoogleCloud`;
    
    tweetTextarea.value = tweetText;
    updateCharCount(tweetText.length);
    
    // Scroll to the sidebar composer smoothly on small screens
    tweetTextarea.focus();
    tweetTextarea.scrollIntoView({ behavior: 'smooth', block: 'center' });
    
    // Highlight the composer
    const widget = document.querySelector('.tweet-composer-widget');
    widget.style.borderColor = 'var(--twitter-blue)';
    widget.style.boxShadow = '0 0 25px var(--twitter-glow)';
    setTimeout(() => {
        widget.style.borderColor = '';
        widget.style.boxShadow = '';
    }, 1500);
}

// Update Character Counter
function updateCharCount(length) {
    charCounter.textContent = length;
    
    const percentage = Math.min((length / 280) * 100, 100);
    charProgressFill.style.width = `${percentage}%`;
    
    // Colors based on length
    if (length > 280) {
        charProgressFill.className = 'error';
        tweetWarningLimit.classList.remove('hidden');
    } else if (length > 250) {
        charProgressFill.className = 'warn';
        tweetWarningLimit.classList.add('hidden');
    } else {
        charProgressFill.className = '';
        tweetWarningLimit.classList.add('hidden');
    }
    
    // Enable/disable tweet button
    btnTweet.disabled = (length === 0);
}

// Open X Share Intent Dialog
function sendTweet() {
    const text = tweetTextarea.value;
    if (!text) return;
    
    const encodedText = encodeURIComponent(text);
    const twitterUrl = `https://x.com/intent/tweet?text=${encodedText}`;
    
    window.open(twitterUrl, '_blank', 'noopener,noreferrer');
}

// Copy to clipboard helper
function copyToClipboard(text, buttonEl) {
    navigator.clipboard.writeText(text).then(() => {
        // Visual feedback
        const originalHTML = buttonEl.innerHTML;
        buttonEl.innerHTML = '<i data-lucide="check" style="color: var(--color-res);"></i>';
        lucide.createIcons();
        
        buttonEl.disabled = true;
        setTimeout(() => {
            buttonEl.innerHTML = originalHTML;
            buttonEl.disabled = false;
            lucide.createIcons();
        }, 1500);
    }).catch(err => {
        console.error('Could not copy text: ', err);
    });
}

// Loader State Management
function showLoading() {
    feedLoading.classList.remove('hidden');
    feedError.classList.add('hidden');
    feedEmpty.classList.add('hidden');
    releasesTimeline.innerHTML = '';
    btnRefresh.classList.add('loading');
    btnRefresh.disabled = true;
    feedResultsCount.textContent = 'Updating...';
}

function hideOverlays() {
    feedLoading.classList.add('hidden');
    feedError.classList.add('hidden');
    feedEmpty.classList.add('hidden');
    btnRefresh.classList.remove('loading');
    btnRefresh.disabled = false;
}

function showError(msg) {
    hideOverlays();
    feedError.classList.remove('hidden');
    document.getElementById('error-description').textContent = msg || 'Failed to fetch release notes feed.';
}

function showEmpty() {
    hideOverlays();
    feedEmpty.classList.remove('hidden');
}
