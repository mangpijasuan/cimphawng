CREATE TABLE `feed_status` (
	`asset` text PRIMARY KEY NOT NULL,
	`success_at` integer,
	`error_at` integer,
	`error_code` text,
	`successes` integer DEFAULT 0 NOT NULL,
	`failures` integer DEFAULT 0 NOT NULL
);
--> statement-breakpoint
CREATE TABLE `operation_receipts` (
	`address` text NOT NULL,
	`key` text NOT NULL,
	`kind` text NOT NULL,
	`payload_hash` text NOT NULL,
	`result` text NOT NULL,
	`created_at` integer NOT NULL,
	PRIMARY KEY(`address`, `key`),
	FOREIGN KEY (`address`) REFERENCES `accounts`(`address`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
ALTER TABLE `sessions` ADD `created_at` integer;