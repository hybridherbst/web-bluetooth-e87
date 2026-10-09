/**
 * Free-space check for uploads.
 *
 * The badge reports its free storage in KB as `memory` in the badge-info reply (Qix 0xC7). Every value seen
 * is a multiple of 4: it is free clusters x 4 KB. A file larger than the free space is accepted all the way
 * through the transfer and only rejected at the very end (cmd 0x1C with status 0x03), so check first.
 */

export const CLUSTER_BYTES = 4096

/**
 * Extra clusters assumed beyond ceil(size / 4096). This is a conservative allowance, not a constant: on an E87 a
 * 131,090-byte file (33 clusters) lowered the free space by 136 KB = 34 clusters, but a 26,693-byte file (7 clusters)
 * lowered it by exactly 28 KB = 7 clusters.
 */
export const OVERHEAD_CLUSTERS = 1

/** Spare clusters to keep free, because the overhead above comes from a single measurement. */
export const SPARE_CLUSTERS = 1

export function clustersNeeded(fileBytes: number): number {
  return Math.ceil(Math.max(0, fileBytes) / CLUSTER_BYTES) + OVERHEAD_CLUSTERS
}

export interface FreeSpaceCheck {
  fits: boolean
  /** Storage the upload is expected to consume, in KB. */
  neededKb: number
  freeKb: number
}

export function checkFreeSpace(freeKb: number, fileBytes: number): FreeSpaceCheck {
  const needed = clustersNeeded(fileBytes)
  const freeClusters = Math.floor((freeKb * 1024) / CLUSTER_BYTES)
  return {
    fits: needed + SPARE_CLUSTERS <= freeClusters,
    neededKb: (needed * CLUSTER_BYTES) / 1024,
    freeKb,
  }
}
