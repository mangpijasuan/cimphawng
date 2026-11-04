CREATE TABLE `accounts` (
	`address` text PRIMARY KEY NOT NULL,
	`balances` text NOT NULL,
	`version` integer DEFAULT 0 NOT NULL,
	`last_op` text DEFAULT '' NOT NULL,
	`created_at` integer NOT NULL,
	`last_seen` integer NOT NULL
);
--> statement-breakpoint
CREATE TABLE `refresh_leases` (
	`key` text PRIMARY KEY NOT NULL,
	`expires` integer NOT NULL
);
--> statement-breakpoint
CREATE TABLE `request_limits` (
	`key` text PRIMARY KEY NOT NULL,
	`count` integer NOT NULL,
	`expires` integer NOT NULL
);
--> statement-breakpoint
CREATE TABLE `api_metrics` (
	`minute` integer NOT NULL,
	`status` integer NOT NULL,
	`count` integer NOT NULL,
	`duration` integer NOT NULL,
	PRIMARY KEY(`minute`, `status`)
);
--> statement-breakpoint
CREATE TABLE `auth_nonces` (
	`nonce` text PRIMARY KEY NOT NULL,
	`address` text NOT NULL,
	`message` text NOT NULL,
	`expires` integer NOT NULL,
	`used` integer DEFAULT 0 NOT NULL
);
--> statement-breakpoint
CREATE TABLE `live_prices` (
	`asset` text PRIMARY KEY NOT NULL,
	`price` text NOT NULL,
	`observed` integer NOT NULL
);
--> statement-breakpoint
CREATE TABLE `sessions` (
	`hash` text PRIMARY KEY NOT NULL,
	`address` text NOT NULL,
	`expires` integer NOT NULL,
	FOREIGN KEY (`address`) REFERENCES `accounts`(`address`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `session_expiry` ON `sessions` (`expires`);--> statement-breakpoint
CREATE TABLE `paper_trades` (
	`id` text PRIMARY KEY NOT NULL,
	`address` text NOT NULL,
	`data` text NOT NULL,
	`created_at` integer NOT NULL,
	`archived` integer DEFAULT 0 NOT NULL,
	FOREIGN KEY (`address`) REFERENCES `accounts`(`address`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `trade_account` ON `paper_trades` (`address`,`created_at`);