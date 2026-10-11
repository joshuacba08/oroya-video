import { TestBed } from '@angular/core/testing';

import { NIcon, provideNeuralIcons } from './icon';

describe('NIcon', () => {
  function render(name: string): HTMLElement {
    TestBed.configureTestingModule({ providers: [provideNeuralIcons()] });
    const fixture = TestBed.createComponent(NIcon);
    fixture.componentRef.setInput('name', name);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it.each(['circle-check', 'columns-2', 'copy', 'layout-grid', 'plug-zap', 'radio', 'wand-sparkles'])(
    'renders the registered icon %s',
    (name) => {
      expect(render(name).querySelector('svg')).not.toBeNull();
    },
  );

  it('falls back instead of throwing on an unknown icon name', () => {
    expect(() => render('definitely-not-an-icon')).not.toThrow();
  });
});
