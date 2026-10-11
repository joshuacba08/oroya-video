import { en } from './en';
import { es } from './es';
import { getLanguage, getLocale, setLanguage, translate } from './i18n';
import { TranslatePipe } from './translate.pipe';

describe('i18n', () => {
  afterEach(() => setLanguage('en'));

  it('translates with interpolation in the active language', () => {
    setLanguage('en');
    expect(translate('dashboard.modelsReady', { count: 3 })).toBe('3 models ready');

    setLanguage('es');
    expect(translate('dashboard.modelsReady', { count: 3 })).toBe('3 modelos listos');
    expect(getLocale()).toBe('es');
    expect(document.documentElement.lang).toBe('es');
  });

  it('falls back for unknown dynamic keys and ignores unsupported languages', () => {
    setLanguage('es');
    expect(translate('status.something_new', undefined, 'something_new')).toBe('something_new');
    expect(translate('errors.unmapped_code', undefined, 'Backend message')).toBe('Backend message');

    setLanguage('fr');
    expect(getLanguage()).toBe('es');
  });

  it('pipe follows language changes', () => {
    const pipe = new TranslatePipe();
    setLanguage('en');
    expect(pipe.transform('common.newProject')).toBe('New Project');
    setLanguage('es');
    expect(pipe.transform('common.newProject')).toBe('Nuevo proyecto');
  });

  it('keeps every placeholder in both languages', () => {
    const placeholders = (text: string) => (text.match(/\{\w+\}/g) ?? []).sort().join(',');
    for (const key of Object.keys(en) as (keyof typeof en)[]) {
      expect(placeholders(es[key]), key).toBe(placeholders(en[key]));
    }
  });
});
