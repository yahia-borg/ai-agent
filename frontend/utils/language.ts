/**
 * Language detection utilities
 */

export function detectLanguage(text: string): 'ar' | 'en' {
    // Check for Arabic characters (Unicode range \u0600-\u06FF)
    const arabicPattern = /[\u0600-\u06FF]/;
    const hasArabic = arabicPattern.test(text);
    
    // Count Arabic vs English characters
    const arabicCount = (text.match(/[\u0600-\u06FF]/g) || []).length;
    const englishCount = (text.match(/[a-zA-Z]/g) || []).length;
    
    // If Arabic characters are present and more than 30% of text, consider it Arabic
    if (hasArabic && arabicCount > text.length * 0.3) {
        return 'ar';
    }
    
    return 'en';
}

export function isRTL(text: string): boolean {
    return detectLanguage(text) === 'ar';
}

