import { Component, input, output } from '@angular/core';

import { NIcon } from './icon';

@Component({
  selector: 'n-sidebar',
  standalone: true,
  template: `<aside class="n-sidebar" [attr.aria-label]="ariaLabel()"><ng-content /></aside>`,
  styles: [
    `
      .n-sidebar {
        position: sticky;
        top: 0;
        display: grid;
        grid-template-rows: auto 1fr auto;
        gap: 20px;
        height: 100vh;
        min-width: 0;
        border-right: 1px solid var(--n-border-1);
        background: linear-gradient(180deg, rgba(20, 18, 45, 0.78), rgba(4, 5, 15, 0.96));
      }

      ::ng-deep [nSidebarBrand] {
        display: flex;
        align-items: center;
        gap: 12px;
        min-width: 0;
        padding: 22px 18px 14px;
      }

      ::ng-deep [nSidebarFooter] {
        align-self: end;
      }

      @media (max-width: 860px) {
        .n-sidebar {
          position: relative;
          height: auto;
          grid-template-rows: auto;
        }
      }
    `,
  ],
})
export class NSidebar {
  readonly ariaLabel = input('Navigation');
}

@Component({
  selector: 'n-sidebar-section',
  standalone: true,
  template: `<nav class="n-sidebar-section"><ng-content /></nav>`,
  styles: [
    `
      .n-sidebar-section {
        display: grid;
        align-content: start;
        gap: 4px;
        padding: 0 12px;
      }
    `,
  ],
})
export class NSidebarSection {}

@Component({
  selector: 'n-sidebar-item',
  standalone: true,
  imports: [NIcon],
  template: `
    <button type="button" class="n-sidebar-item" [class.active]="active()" (click)="itemClick.emit()">
      <n-icon [name]="icon()" size="md" />
      <span>{{ label() }}</span>
      @if (badge()) {
        <strong>{{ badge() }}</strong>
      }
    </button>
  `,
  styles: [
    `
      .n-sidebar-item {
        display: grid;
        grid-template-columns: 26px minmax(0, 1fr) auto;
        align-items: center;
        gap: 12px;
        width: 100%;
        min-height: 50px;
        padding: 0 10px;
        border: 0;
        border-left: 3px solid transparent;
        border-radius: 0 var(--n-radius-md) var(--n-radius-md) 0;
        background: transparent;
        color: var(--n-text-3);
        font: inherit;
        font-size: 0.9rem;
        font-weight: 800;
        text-align: left;
        cursor: pointer;
      }

      .n-sidebar-item span {
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .n-sidebar-item.active,
      .n-sidebar-item:hover {
        border-left-color: #6d7cff;
        background: rgba(73, 122, 255, 0.12);
        color: #8ab4ff;
      }

      .n-sidebar-item strong {
        display: inline-grid;
        place-items: center;
        min-width: 22px;
        height: 20px;
        padding: 0 6px;
        border-radius: var(--n-radius-full);
        background: #6875ff;
        color: #fff;
        font-size: 0.68rem;
      }
    `,
  ],
})
export class NSidebarItem {
  readonly icon = input('');
  readonly label = input('');
  readonly badge = input<string | undefined>(undefined);
  readonly active = input(false);
  readonly itemClick = output<void>();
}
