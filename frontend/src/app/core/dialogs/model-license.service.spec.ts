import { TestBed } from '@angular/core/testing';

import type { ModelVm } from '../models/oroya.models';
import { DialogService } from './dialog.service';
import { ModelLicenseService } from './model-license.service';

function model(overrides: Partial<ModelVm>): ModelVm {
  return {
    id: 'id',
    slug: 'slug',
    name: 'Model',
    version: '',
    description: '',
    installed: false,
    enabled: true,
    qualityTier: '',
    speedTier: '',
    quality: 0,
    speed: 0,
    vramGb: 1,
    category: 'upscaling',
    license: 'MIT',
    nonCommercial: false,
    ...overrides,
  };
}

describe('ModelLicenseService', () => {
  let service: ModelLicenseService;
  let dialogs: DialogService;

  beforeEach(() => {
    service = TestBed.inject(ModelLicenseService);
    dialogs = TestBed.inject(DialogService);
  });

  it('downloads permissive models without asking', async () => {
    await expect(service.acceptDownload(model({}))).resolves.toBe(true);
    expect(dialogs.current()).toBeNull();
  });

  it('asks before downloading a non-commercial model and respects the answer', async () => {
    const gfpgan = model({ name: 'GFPGAN v1.4', nonCommercial: true });

    const declined = service.acceptDownload(gfpgan);
    expect(dialogs.current()?.kind).toBe('confirm');
    expect(dialogs.current()?.title).toContain('GFPGAN v1.4');
    dialogs.close(false);
    await expect(declined).resolves.toBe(false);

    const accepted = service.acceptDownload(gfpgan);
    dialogs.close(true);
    await expect(accepted).resolves.toBe(true);
  });
});
