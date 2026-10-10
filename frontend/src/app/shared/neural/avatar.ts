import { Component, computed, input } from '@angular/core';

@Component({
  selector: 'n-avatar',
  standalone: true,
  template: `<span class="n-avatar">{{ initials() }}</span>`,
  styles: [
    `
      :host {
        display: inline-grid;
        place-items: center;
        width: 36px;
        height: 36px;
        border-radius: 50%;
        background: var(--n-gradient-primary-secondary);
        color: #fff;
        font-size: 0.78rem;
        font-weight: 900;
      }

      .n-avatar {
        line-height: 1;
      }
    `,
  ],
})
export class NAvatar {
  readonly name = input('');
  readonly size = input<'xs' | 'sm' | 'md' | 'lg'>('md');

  readonly initials = computed(() =>
    this.name()
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join('') || 'OV',
  );
}
