import type { InferenceSession, Tensor } from 'onnxruntime-web';
import type { FrameObservation } from './student_signal_tracker.mjs';

export const DETECTOR_INPUT_SIZE = 320;
export const COCO_PERSON_CLASS_ID = 1;
export const COCO_CELL_PHONE_CLASS_ID = 77;
export const BODY_CROP_BANDS = [
  [0.35, 1.0],
  [0.5, 1.1],
  [0.25, 0.9],
] as const;
export const BODY_CROP_SIDE_PADDING = 0.15;
export const MINIMUM_CROP_PIXELS = 20;

export interface ImageDataLike {
  data: ArrayLike<number>;
  width: number;
  height: number;
}

export type DetectionRow = readonly [number, number, number, number, number, number];

export interface CropRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

interface ModelManifest {
  sha256: string;
  is_approved: boolean;
  input_size: number;
  output_format?: string;
}

type SessionOptions = InferenceSession.SessionOptions;
type SessionFactory = (
  model: ArrayBuffer,
  options: SessionOptions,
) => Promise<InferenceSession>;

type OrtRuntime = {
  env: {
    wasm: {
      numThreads: number;
      proxy: boolean;
      wasmPaths: string;
    };
  };
  InferenceSession: {
    create: SessionFactory;
  };
  Tensor: new (type: 'float32', data: Float32Array, dims: readonly number[]) => Tensor;
};

/**
 * Converts RGBA image data into the detector's RGB NCHW tensor layout.
 *
 * @param image - ImageData-like pixels in row-major RGBA order.
 * @returns Normalized RGB channels in NCHW order.
 */
export function toInputTensor(image: ImageDataLike): Float32Array {
  const pixels = image.width * image.height;
  const tensor = new Float32Array(pixels * 3);
  for (let index = 0; index < pixels; index += 1) {
    const source = index * 4;
    tensor[index] = Number(image.data[source]) / 255;
    tensor[pixels + index] = Number(image.data[source + 1]) / 255;
    tensor[pixels * 2 + index] = Number(image.data[source + 2]) / 255;
  }
  return tensor;
}

/**
 * Returns the highest finite detector score for one COCO class.
 *
 * @param rows - Normalized detector rows.
 * @param classId - COCO class identifier to select.
 * @returns The highest score, or zero when the class is absent.
 */
export function bestScore(rows: readonly DetectionRow[], classId: number): number {
  return rows.reduce(
    (best, row) => (row[5] === classId && Number.isFinite(row[4]) ? Math.max(best, row[4]) : best),
    0,
  );
}

/**
 * Computes the person's padded body crops used to recover small phone detections.
 *
 * @param rows - Normalized detector rows.
 * @param width - Source frame width in pixels.
 * @param height - Source frame height in pixels.
 * @returns Valid body crop rectangles in source-frame pixels.
 */
export function bodyCropRects(
  rows: readonly DetectionRow[],
  width: number,
  height: number,
): CropRect[] {
  const people = rows.filter((row) => row[5] === COCO_PERSON_CLASS_ID);
  const best = people.reduce<DetectionRow | null>(
    (candidate, row) => (candidate === null || row[4] > candidate[4] ? row : candidate),
    null,
  );
  if (!best) return [];
  const [x1, y1, x2, y2] = best;
  const left = x1 * width;
  const top = y1 * height;
  const boxWidth = (x2 - x1) * width;
  const boxHeight = (y2 - y1) * height;
  return BODY_CROP_BANDS.flatMap(([bandTop, bandBottom]) => {
    const cropLeft = Math.max(0, Math.floor(left - BODY_CROP_SIDE_PADDING * boxWidth));
    const cropRight = Math.min(
      width,
      Math.floor(left + boxWidth + BODY_CROP_SIDE_PADDING * boxWidth),
    );
    const cropTop = Math.max(0, Math.floor(top + bandTop * boxHeight));
    const cropBottom = Math.min(height, Math.floor(top + bandBottom * boxHeight));
    if (
      cropRight - cropLeft <= MINIMUM_CROP_PIXELS ||
      cropBottom - cropTop <= MINIMUM_CROP_PIXELS
    ) {
      return [];
    }
    return [
      {
        left: cropLeft,
        top: cropTop,
        width: cropRight - cropLeft,
        height: cropBottom - cropTop,
      },
    ];
  });
}

/**
 * Runs the approved local person/phone model against browser camera pixels.
 */
export class OnnxStudentFrameAnalyzer {
  private readonly session: InferenceSession;

  private readonly canvas: OffscreenCanvas | HTMLCanvasElement;

  private readonly context: CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D;

  private constructor(session: InferenceSession) {
    this.session = session;
    this.canvas =
      typeof OffscreenCanvas === 'undefined'
        ? Object.assign(document.createElement('canvas'), {
            width: DETECTOR_INPUT_SIZE,
            height: DETECTOR_INPUT_SIZE,
          })
        : new OffscreenCanvas(DETECTOR_INPUT_SIZE, DETECTOR_INPUT_SIZE);
    this.canvas.width = DETECTOR_INPUT_SIZE;
    this.canvas.height = DETECTOR_INPUT_SIZE;
    const context = this.canvas.getContext('2d', { willReadFrequently: true });
    if (!context) throw new Error('The local camera canvas is unavailable.');
    this.context = context;
  }

  /**
   * Fetches and verifies the approved detector before creating a WASM session.
   *
   * @param modelUrl - URL for the committed ONNX model.
   * @param manifestUrl - URL for the adjacent model manifest.
   * @param sessionFactory - Optional test seam for session creation.
   * @returns A ready local frame analyzer.
   * @throws Error If the manifest, digest, or ONNX session is unsupported.
   */
  public static async load(
    modelUrl: string,
    manifestUrl: string,
    sessionFactory?: SessionFactory,
  ): Promise<OnnxStudentFrameAnalyzer> {
    const manifestResponse = await fetch(manifestUrl);
    if (!manifestResponse.ok) throw new Error('The local detector manifest could not be loaded.');
    const manifest = (await manifestResponse.json()) as Partial<ModelManifest>;
    if (
      manifest.is_approved !== true ||
      manifest.input_size !== DETECTOR_INPUT_SIZE ||
      typeof manifest.sha256 !== 'string'
    ) {
      throw new Error('The local detector manifest is not approved for this app.');
    }
    const modelResponse = await fetch(modelUrl);
    if (!modelResponse.ok) throw new Error('The local detector model could not be loaded.');
    const model = await modelResponse.arrayBuffer();
    const digest = await crypto.subtle.digest('SHA-256', model);
    const actualHash = [...new Uint8Array(digest)]
      .map((byte) => byte.toString(16).padStart(2, '0'))
      .join('');
    if (actualHash !== manifest.sha256) throw new Error('The local detector digest does not match.');

    const factory =
      sessionFactory ??
      (async (bytes: ArrayBuffer, options: SessionOptions): Promise<InferenceSession> => {
        const runtime = (await import(
          new URL('../../vendor/ort/ort.wasm.min.mjs', import.meta.url).href
        )) as unknown as OrtRuntime;
        runtime.env.wasm.numThreads = 1;
        runtime.env.wasm.proxy = false;
        runtime.env.wasm.wasmPaths = new URL('../../vendor/ort/', import.meta.url).href;
        return runtime.InferenceSession.create(bytes, options);
      });
    const session = await factory(model, { executionProviders: ['wasm'] });
    if (!session.inputNames.includes('image') || !session.outputNames.includes('detections')) {
      throw new Error('The local detector tensor contract is unsupported.');
    }
    return new OnnxStudentFrameAnalyzer(session);
  }

  /**
   * Produces person and phone scores from one local camera frame.
   *
   * @param source - Camera image source that remains in the renderer.
   * @param width - Source frame width.
   * @param height - Source frame height.
   * @returns Derived scores with no frame or detection boxes.
   */
  public async analyze(
    source: CanvasImageSource,
    width: number,
    height: number,
  ): Promise<FrameObservation> {
    if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
      throw new Error('The local camera frame dimensions are invalid.');
    }
    this.context.drawImage(source, 0, 0, width, height, 0, 0, DETECTOR_INPUT_SIZE, DETECTOR_INPUT_SIZE);
    const fullRows = await this.runCanvas();
    const personScore = bestScore(fullRows, COCO_PERSON_CLASS_ID);
    let phoneScore = bestScore(fullRows, COCO_CELL_PHONE_CLASS_ID);
    for (const crop of bodyCropRects(fullRows, width, height)) {
      this.context.clearRect(0, 0, DETECTOR_INPUT_SIZE, DETECTOR_INPUT_SIZE);
      this.context.drawImage(
        source,
        crop.left,
        crop.top,
        crop.width,
        crop.height,
        0,
        0,
        DETECTOR_INPUT_SIZE,
        DETECTOR_INPUT_SIZE,
      );
      phoneScore = Math.max(phoneScore, bestScore(await this.runCanvas(), COCO_CELL_PHONE_CLASS_ID));
    }
    this.context.clearRect(0, 0, DETECTOR_INPUT_SIZE, DETECTOR_INPUT_SIZE);
    return { personScore, phoneScore };
  }

  /**
   * Releases the local ONNX session.
   */
  public dispose(): void {
    void this.session.release();
  }

  private async runCanvas(): Promise<DetectionRow[]> {
    const image = this.context.getImageData(0, 0, DETECTOR_INPUT_SIZE, DETECTOR_INPUT_SIZE);
    const input = toInputTensor(image);
    let tensor: Tensor | undefined;
    try {
      const runtime = (await import(
        new URL('../../vendor/ort/ort.wasm.min.mjs', import.meta.url).href
      )) as unknown as OrtRuntime;
      tensor = new runtime.Tensor('float32', input, [
        1,
        3,
        DETECTOR_INPUT_SIZE,
        DETECTOR_INPUT_SIZE,
      ]);
      const output = (await this.session.run({ image: tensor })).detections;
      const data = output?.data;
      const dims = output?.dims;
      if (
        !data ||
        !dims ||
        dims.length !== 2 ||
        dims[1] !== 6 ||
        dims[0] > 1000 ||
        data.length !== dims[0] * dims[1]
      ) {
        throw new Error('The local detector output tensor is unsupported.');
      }
      const rows: DetectionRow[] = [];
      for (let offset = 0; offset < data.length; offset += 6) {
        const row = Array.from(data.slice(offset, offset + 6), Number) as unknown as DetectionRow;
        if (!row.every(Number.isFinite)) throw new Error('The local detector output is invalid.');
        rows.push(row);
      }
      return rows;
    } finally {
      input.fill(0);
      if (tensor?.data instanceof Float32Array) tensor.data.fill(0);
    }
  }
}
