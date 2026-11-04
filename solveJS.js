function longestUniqueSubstring(str) {
    if (str === '') return '';
    
    const lastSeen = new Map();
    let left = 0;
    let bestStart = 0;
    let maxLen = 0;

    for(let right = 0; right < str.length; right++) {
        const char = str[right];

        if (lastSeen.has(char) && lastSeen.get(char) >= left) {
            left = lastSeen.get(char) + 1;
        }

        lastSeen.set(char, right);

        const windowLen = right - left + 1;
        if (windowLen > maxLen) {
            maxLen = windowLen;
            bestStart = left;
        }
    }

    return str.slice(bestStart, bestStart + maxLen);
}