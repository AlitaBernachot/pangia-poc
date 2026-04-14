import { useTranslation } from 'react-i18next'
import { SUPPORTED_LANGUAGES, type LanguageCode } from '../../i18n/i18n'

export function LanguageSwitcher() {
  const { i18n, t } = useTranslation()

  const handleChange = (code: LanguageCode) => {
    i18n.changeLanguage(code)
    localStorage.setItem('pangia-language', code)
  }

  return (
    <div className="flex items-center gap-1" aria-label={t('languageSwitcher.label')}>
      {SUPPORTED_LANGUAGES.map((lang) => (
        <button
          key={lang.code}
          type="button"
          onClick={() => handleChange(lang.code)}
          className={`px-2 py-1 rounded-md text-xs font-medium transition-colors ${
            i18n.language === lang.code
              ? 'text-white bg-white/10'
              : 'text-white/40 hover:text-white/70 hover:bg-white/5'
          }`}
        >
          {lang.label}
        </button>
      ))}
    </div>
  )
}
