import { Injectable, effect, inject } from '@angular/core';
import { Title } from '@angular/platform-browser';
import { type RouterStateSnapshot, TitleStrategy } from '@angular/router';

import { getLanguage, translate } from './i18n';

/** Los `title` de las rutas son claves de traducción; se re-traducen al cambiar el idioma. */
@Injectable({ providedIn: 'root' })
export class TranslatedTitleStrategy extends TitleStrategy {
  private readonly title = inject(Title);
  private titleKey: string | undefined;

  constructor() {
    super();
    effect(() => {
      getLanguage();
      this.apply();
    });
  }

  override updateTitle(snapshot: RouterStateSnapshot): void {
    this.titleKey = this.buildTitle(snapshot);
    this.apply();
  }

  private apply(): void {
    this.title.setTitle(
      this.titleKey ? `Oroya Video - ${translate(this.titleKey)}` : 'Oroya Video',
    );
  }
}
